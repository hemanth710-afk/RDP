from brain.editing_plan import EditingAction, EditingPlan
from brain.executor import EditingPlanExecutor
from brain.ae_handlers import AEAutomationHandlers
from ae_automation import AEAutomationCommands


def main():
    commands = AEAutomationCommands()

    handlers = AEAutomationHandlers(commands)

    executor = EditingPlanExecutor(
        actions=type(
            "StopController",
            (),
            {"check_stop": lambda self: None},
        )(),
        handlers=handlers.handlers(),
    )

    plan = EditingPlan(
        title="AI EDITOR First Composition",
        duration=10.0,
        frame_rate=30.0,
        width=1080,
        height=1920,
        actions=(
            EditingAction(
                action="create_project",
            ),
            EditingAction(
                action="create_composition",
                parameters={
                    "name": "AI EDITOR TEST",
                    "width": 1080,
                    "height": 1920,
                    "duration": 10.0,
                    "frame_rate": 30.0,
                    "background_color": (
                        0.0,
                        0.0,
                        0.0,
                    ),
                },
            ),
        ),
    )

    print("APPROVED PLAN:", plan.title)
    print("ACTIONS:", plan.action_count)
    print()
    print("EXECUTING REAL AE OPERATION...")

    executor.execute(plan)

    print()
    print("REAL AE COMPOSITION OPERATION OK")


if __name__ == "__main__":
    main()