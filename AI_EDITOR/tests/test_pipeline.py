import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ae_automation.commands import AEAutomationCommands
from ae_automation.script_runner import AEScriptRunner
from app_control.controller import ApplicationController
from app_control.file_explorer import FileExplorerController, FileExplorerError
from brain.ae_handlers import AEAutomationHandlers
from brain.amv_script import AMVScript, ClipReference
from brain.editing_plan import EditingAction, EditingPlan
from brain.executor import EditingPlanExecutor, ExecutorError
from brain.plan_parser import EditingPlanParser
from brain.project_state import ProjectPhase, ProjectState
from main import run_pipeline


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_runner = MagicMock(spec=AEScriptRunner)
        self.commands = AEAutomationCommands(runner=self.mock_runner)
        self.handlers = AEAutomationHandlers(self.commands)

    def test_all_parser_allowed_actions_have_registered_handlers(self):
        parser_actions = EditingPlanParser.ALLOWED_ACTIONS
        registered_handlers = self.handlers.handlers()
        
        for action in parser_actions:
            self.assertIn(
                action,
                registered_handlers,
                msg=f"Parser allowed action '{action}' is missing a registered handler in AEAutomationHandlers!"
            )

    def test_new_action_handlers_call_commands(self):
        # add_null
        action_null = EditingAction(
            action="add_null",
            parameters={"composition_name": "Comp 1", "layer_name": "Null 1"}
        )
        self.handlers.add_null(action_null)
        self.mock_runner.run.assert_called()

        # add_adjustment_layer
        self.mock_runner.reset_mock()
        action_adj = EditingAction(
            action="add_adjustment_layer",
            parameters={"composition_name": "Comp 1", "layer_name": "Adj 1"}
        )
        self.handlers.add_adjustment_layer(action_adj)
        self.mock_runner.run.assert_called()

        # rename_layer
        self.mock_runner.reset_mock()
        action_rename = EditingAction(
            action="rename_layer",
            parameters={"composition_name": "Comp 1", "layer_name": "Old", "new_name": "New"}
        )
        self.handlers.rename_layer(action_rename)
        self.mock_runner.run.assert_called()

        # set_enabled
        self.mock_runner.reset_mock()
        action_enabled = EditingAction(
            action="set_enabled",
            parameters={"composition_name": "Comp 1", "layer_name": "Layer 1", "enabled": True}
        )
        self.handlers.set_enabled(action_enabled)
        self.mock_runner.run.assert_called()

    def test_application_controller_file_explorer(self):
        fe_controller = MagicMock(spec=FileExplorerController)
        app_ctrl = ApplicationController(file_explorer=fe_controller)

        app_ctrl.open_file_explorer("C:\\")
        fe_controller.open.assert_called_once_with("C:\\")

    def test_end_to_end_pipeline_execution(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)

            # Create an AMV Script file
            script = AMVScript(
                title="Integration Test AMV",
                target_duration=30.0,
                clips=[ClipReference(path="clip1.mp4", clip_id="c1")]
            )
            script_file = tempdir_path / "amv_script.json"
            script_file.write_text(
                json_dumps_script(script),
                encoding="utf-8"
            )

            # Create an Editing Plan file
            plan = EditingPlan(
                title="Integration Test AMV",
                duration=30.0,
                actions=[
                    EditingAction(action="create_project", parameters={}),
                    EditingAction(
                        action="create_composition",
                        parameters={"name": "AMV_Comp", "width": 1920, "height": 1080, "duration": 30.0}
                    ),
                    EditingAction(
                        action="cut",
                        parameters={
                            "composition_name": "AMV_Comp",
                            "layer_name": "clip1.mp4",
                            "timeline_start": 0.0,
                            "timeline_end": 5.0,
                            "source_start": 0.0
                        }
                    )
                ]
            )
            plan_file = tempdir_path / "editing_plan.json"
            plan_file.write_text(
                json_dumps_plan(plan),
                encoding="utf-8"
            )

            # Run full pipeline with mock runner
            final_state = run_pipeline(
                script_path=str(script_file),
                plan_path_arg=str(plan_file),
                state_dir_arg=tempdir,
                execute=True,
                ae_runner=self.mock_runner
            )

            self.assertEqual(final_state.phase, ProjectPhase.COMPLETED)
            self.assertEqual(final_state.completed_action_index, 2)
            self.assertEqual(final_state.total_actions, 3)
            self.assertEqual(self.mock_runner.run.call_count, 3)

    def test_checkpoint_resume_simulation(self):
        """Simulate action failures, checkpoint persistence, and resume functionality.
        
        Verifies:
        - Actions 0-2 succeed.
        - Action 3 fails.
        - Execution state (completed index, phase, failure error) is saved.
        - Resuming execution starts exactly at action 3.
        - Actions 0-2 are NOT repeated.
        - Re-running to successful completion marks state as COMPLETED.
        """
        plan = EditingPlan(
            title="Resume Simulation Plan",
            duration=10.0,
            actions=[
                EditingAction(action="act0", parameters={}),
                EditingAction(action="act1", parameters={}),
                EditingAction(action="act2", parameters={}),
                EditingAction(action="act3", parameters={}),
                EditingAction(action="act4", parameters={}),
            ]
        )

        called_indices = []

        # Handlers that fail at index 3
        def make_handler(index, should_fail=False):
            def handler(action):
                called_indices.append(index)
                if should_fail:
                    raise RuntimeError(f"Simulated failure at action {index}")
            return handler

        handlers_first_run = {
            "act0": make_handler(0),
            "act1": make_handler(1),
            "act2": make_handler(2),
            "act3": make_handler(3, should_fail=True),
            "act4": make_handler(4),
        }

        # Mock visible actions stop checker
        actions_mock = MagicMock()
        actions_mock.check_stop = MagicMock()

        executor = EditingPlanExecutor(actions=actions_mock, handlers=handlers_first_run)
        state = ProjectState(total_actions=len(plan.actions))

        # First run simulation
        start_index = 0
        def on_progress_first(index, action):
            state.mark_action_completed(index)

        with self.assertRaises(ExecutorError) as context:
            executor.execute_from(plan, start_index=start_index, on_progress=on_progress_first)

        self.assertIn("Simulated failure at action 3", str(context.exception))
        
        # Action 3 failed, so completed index is 2
        state.mark_failed(3, str(context.exception))

        self.assertEqual(state.completed_action_index, 2)
        self.assertEqual(state.failed_action_index, 3)
        self.assertEqual(state.phase, ProjectPhase.FAILED)
        self.assertEqual(called_indices, [0, 1, 2, 3])

        # Verify next action index is 3
        self.assertEqual(state.next_action_index, 3)
        self.assertTrue(state.is_resumable)

        # Clear tracking list for second run
        called_indices.clear()

        # Handlers for second run (where action 3 now succeeds)
        handlers_second_run = {
            "act0": make_handler(0),
            "act1": make_handler(1),
            "act2": make_handler(2),
            "act3": make_handler(3, should_fail=False),
            "act4": make_handler(4),
        }

        executor_resume = EditingPlanExecutor(actions=actions_mock, handlers=handlers_second_run)
        
        # Update phase to executing to simulate restart resume
        state.advance_phase(ProjectPhase.EXECUTING)

        resume_start_index = state.next_action_index # starts at 3
        self.assertEqual(resume_start_index, 3)

        def on_progress_second(index, action):
            state.mark_action_completed(index)

        # Resume execution
        executor_resume.execute_from(plan, start_index=resume_start_index, on_progress=on_progress_second)

        # Successful completion
        state.advance_phase(ProjectPhase.COMPLETED)

        # Check called indices: only 3 and 4 should have run!
        self.assertEqual(called_indices, [3, 4])
        self.assertEqual(state.completed_action_index, 4)
        self.assertEqual(state.phase, ProjectPhase.COMPLETED)


def json_dumps_script(script: AMVScript) -> str:
    import json
    return json.dumps(script.to_dict(), indent=2)

def json_dumps_plan(plan: EditingPlan) -> str:
    import json
    return json.dumps(plan.to_dict(), indent=2)


if __name__ == "__main__":
    unittest.main()
