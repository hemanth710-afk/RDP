"""AI_EDITOR — Professional AMV Editor CLI entry point.

Pipeline:
    SCRIPT → UNDERSTANDING → SOURCE ANALYSIS → AI PLAN
    → VALIDATION → APPROVAL → EXECUTION → CHECKPOINT → AFTER EFFECTS → DONE
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app_control import (
    AfterEffectsController,
    ApplicationController,
    ChromeController,
    FileExplorerController,
)
from ae_automation import AEAutomationCommands, AEScriptRunner
from brain.ae_handlers import AEAutomationHandlers
from brain.amv_script import AMVScript, AMVScriptError
from brain.approval import ApprovalError, EditingPlanApproval
from brain.editing_plan import EditingAction, EditingPlan
from brain.executor import EditingPlanExecutor, ExecutorError
from brain.logging_config import setup_logging
from brain.plan_parser import EditingPlanParser, PlanParserError
from brain.planner import AIEditingPlanner, PlannerError
from brain.project_state import ProjectPhase, ProjectState
from config.model_config import ModelConfig
from interface.ai_chat import AIChatProvider
from interface.chat import AIChatSession

logger = logging.getLogger("ai_editor.main")


def load_script(script_path: str) -> AMVScript:
    """Load an AMV script/brief from a JSON file."""
    logger.info("Loading AMV script: %s", script_path)

    try:
        script = AMVScript.from_json_file(script_path)
    except (AMVScriptError, FileNotFoundError) as exc:
        logger.error("Failed to load AMV script: %s", exc)
        raise SystemExit(f"Script error: {exc}") from exc

    logger.info(
        "Loaded script: %s (duration=%s, clips=%d)",
        script.title,
        script.target_duration,
        len(script.clips),
    )

    return script


def validate_sources(script: AMVScript) -> list[str]:
    """Validate that referenced source files exist."""
    missing = script.validate_paths()

    if missing:
        for path in missing:
            logger.warning("Missing source file: %s", path)
        logger.warning(
            "%d source file(s) not found. "
            "Proceeding — AI will work with available assets.",
            len(missing),
        )

    return missing


def load_or_create_state(state_path: Path) -> ProjectState:
    """Load existing project state or create a new one."""
    if state_path.exists():
        logger.info("Resuming from checkpoint: %s", state_path)
        state = ProjectState.load(state_path)
        logger.info(
            "Project %s — phase=%s, completed=%d/%d",
            state.project_id,
            state.phase.value,
            state.completed_action_index + 1,
            state.total_actions,
        )
        return state

    state = ProjectState()
    state.advance_phase(ProjectPhase.INITIALIZED)
    return state


def save_plan(plan: EditingPlan, plan_path: Path) -> None:
    """Save a validated editing plan to disk."""
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(plan.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Plan saved: %s", plan_path)


def load_plan(plan_path: Path) -> EditingPlan:
    """Load a previously saved editing plan."""
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    return EditingPlan.from_dict(data)


def print_plan_summary(plan: EditingPlan) -> None:
    """Print a concise human-readable plan summary."""
    print(f"\n{'='*60}")
    print(f"  AMV EDITING PLAN: {plan.title}")
    print(f"{'='*60}")
    print(f"  Duration:    {plan.duration:.1f}s")
    print(f"  Resolution:  {plan.width}x{plan.height}")
    print(f"  Frame rate:  {plan.frame_rate:g} FPS")
    print(f"  Actions:     {plan.action_count}")
    print(f"  Source files: {len(plan.source_files)}")

    if plan.notes:
        print(f"  Notes:       {plan.notes[:200]}")

    print(f"{'='*60}")

    action_counts: dict[str, int] = {}
    for action in plan.actions:
        action_counts[action.action] = (
            action_counts.get(action.action, 0) + 1
        )

    print("  Action breakdown:")
    for name, count in sorted(action_counts.items()):
        print(f"    {name}: {count}")

    print(f"{'='*60}\n")


def run_pipeline(
    script_path: str | None = None,
    plan_path_arg: str | None = None,
    state_dir_arg: str = ".",
    log_file: str | None = None,
    validate_only: bool = False,
    show_plan: bool = False,
    auto_approve: bool = False,
    execute: bool = False,
    ae_runner: AEScriptRunner | None = None,
) -> ProjectState:
    """Execute the AI_EDITOR AMV pipeline end-to-end."""
    setup_logging(log_file=log_file)
    logger.info("AI_EDITOR pipeline starting.")

    state_dir = Path(state_dir_arg)
    state_path = state_dir / "project_state.json"
    plan_path = state_dir / "editing_plan.json"

    # 1. Load or create state
    state = load_or_create_state(state_path)

    # 2. Load AMV script if provided
    script: AMVScript | None = None
    if script_path:
        script = load_script(script_path)
        validate_sources(script)
        state.script_path = script_path
        state.advance_phase(ProjectPhase.SCRIPT_LOADED)
        state.save(state_path)

    # 3. Load plan from file or state
    plan: EditingPlan | None = None
    if plan_path_arg:
        logger.info("Loading plan from specified file: %s", plan_path_arg)
        try:
            plan = load_plan(Path(plan_path_arg))
        except Exception as exc:
            logger.error("Failed to load plan file: %s", exc)
            raise SystemExit(f"Plan load error: {exc}") from exc
    elif plan_path.exists() and state.phase in (
        ProjectPhase.PLAN_GENERATED,
        ProjectPhase.PLAN_APPROVED,
        ProjectPhase.EXECUTING,
        ProjectPhase.FAILED,
    ):
        logger.info("Loading existing saved plan: %s", plan_path)
        plan = load_plan(plan_path)

    # 4. Generate plan via AI if script loaded but no plan exists
    if script and not plan and not validate_only:
        logger.info("Generating AI editing plan for script: %s", script.title)
        try:
            from models.provider_factory import create_provider
            config = ModelConfig.from_environment()
            chat_provider = create_provider(config)
            planner = AIEditingPlanner(chat_provider=chat_provider)
            session = AIChatSession()

            amv_context = planner.build_amv_context(
                title=script.title,
                song_path=script.song_path,
                clip_inventory=script.clip_inventory_summary(),
                target_duration=script.target_duration,
                lyrics=script.lyrics,
                mood=script.mood,
                editing_style=script.editing_style,
                special_requirements=script.special_requirements,
                notes=script.notes,
                frame_rate=script.frame_rate,
                width=script.width,
                height=script.height,
            )

            plan = planner.generate(session, amv_context=amv_context)
            save_plan(plan, plan_path)
            state.plan_path = str(plan_path)
            state.total_actions = plan.action_count
            state.advance_phase(ProjectPhase.PLAN_GENERATED)
            state.save(state_path)
        except Exception as exc:
            logger.error("AI Plan generation failed: %s", exc)
            if not plan_path_arg:
                logger.info(
                    "AI plan generation failed (e.g. invalid API key). "
                    "You can supply a pre-generated plan with --plan."
                )

    if plan and show_plan:
        print_plan_summary(plan)
        if not execute and not validate_only:
            return state

    if validate_only:
        if script:
            print(f"Script valid: {script.title}")
        if plan:
            print_plan_summary(plan)
            print("Plan validation: PASSED")
        return state

    if not script and not plan:
        logger.info("No script or plan provided.")
        return state

    if plan and (execute or auto_approve or state.phase == ProjectPhase.EXECUTING):
        # 5. Approval Gate
        approval_gate = EditingPlanApproval()
        approval_gate.submit(plan)
        approved_plan = approval_gate.approve()

        if state.phase != ProjectPhase.EXECUTING:
            state.advance_phase(ProjectPhase.PLAN_APPROVED)
            state.total_actions = approved_plan.action_count
            state.save(state_path)

        # 6. Prepare Execution & Controllers
        logger.info("Starting execution of approved plan: %s", approved_plan.title)
        state.advance_phase(ProjectPhase.EXECUTING)
        state.save(state_path)

        commands = AEAutomationCommands(runner=ae_runner)
        ae_handlers = AEAutomationHandlers(commands)
        handlers_dict = ae_handlers.handlers()

        # Simple stop check interface wrapper
        class SimpleStopChecker:
            def check_stop(self) -> None:
                pass

        stop_checker = SimpleStopChecker()
        executor = EditingPlanExecutor(actions=stop_checker, handlers=handlers_dict)

        start_index = state.next_action_index if state.completed_action_index >= 0 else 0

        def on_action_progress(index: int, action: EditingAction) -> None:
            state.mark_action_completed(index)
            state.save(state_path)
            logger.info(
                "Checkpoint: Action %d/%d (%s) succeeded.",
                index + 1,
                approved_plan.action_count,
                action.action,
            )

        try:
            executor.execute_from(
                approved_plan,
                start_index=start_index,
                on_progress=on_action_progress,
            )
            state.advance_phase(ProjectPhase.COMPLETED)
            state.save(state_path)
            logger.info("Pipeline execution completed successfully!")
        except Exception as exc:
            failed_idx = state.next_action_index
            logger.error("Execution failed at action index %d: %s", failed_idx, exc)
            state.mark_failed(failed_idx, str(exc))
            state.save(state_path)

    return state


def main() -> None:
    """CLI entry point for AI_EDITOR."""
    parser = argparse.ArgumentParser(
        description="AI_EDITOR — Professional AMV Editor",
    )
    parser.add_argument(
        "script",
        nargs="?",
        help="Path to AMV script/brief JSON file",
    )
    parser.add_argument(
        "--plan",
        help="Path to a pre-generated plan JSON file to execute",
    )
    parser.add_argument(
        "--state-dir",
        default=".",
        help="Directory for project state and checkpoints",
    )
    parser.add_argument(
        "--log-file",
        help="Optional log file path",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate script and plan without executing",
    )
    parser.add_argument(
        "--show-plan",
        action="store_true",
        help="Show plan summary and exit",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute plan immediately in After Effects",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve plan and execute",
    )

    args = parser.parse_args()

    run_pipeline(
        script_path=args.script,
        plan_path_arg=args.plan,
        state_dir_arg=args.state_dir,
        log_file=args.log_file,
        validate_only=args.validate_only,
        show_plan=args.show_plan,
        auto_approve=args.auto_approve,
        execute=args.execute or args.auto_approve,
    )


if __name__ == "__main__":
    main()
