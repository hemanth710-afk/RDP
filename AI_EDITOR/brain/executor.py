"""Controlled executor for approved AI editing plans.

Only explicitly supported action names may reach the execution layer.
The executor never evaluates AI-generated Python or shell commands.
"""

from __future__ import annotations

from typing import Callable, Mapping

from ae_visual.actions import AEVisibleActions, AEActionStopped

from .editing_plan import EditingAction, EditingPlan


class ExecutorError(RuntimeError):
    """Raised when an approved editing plan cannot be executed."""


class EditingPlanExecutor:
    """Execute approved editing actions through registered handlers."""

    def __init__(
        self,
        actions: AEVisibleActions,
        handlers: Mapping[
            str,
            Callable[[EditingAction], None],
        ],
    ) -> None:
        self.actions = actions
        self.handlers = dict(handlers)

    def execute(
        self,
        plan: EditingPlan,
    ) -> None:
        """Execute every action in an approved editing plan."""

        if not isinstance(plan, EditingPlan):
            raise TypeError(
                "plan must be an EditingPlan."
            )

        for index, action in enumerate(plan.actions):
            self.actions.check_stop()

            handler = self.handlers.get(
                action.action
            )

            if handler is None:
                raise ExecutorError(
                    f"No execution handler is registered for "
                    f"action {index}: {action.action!r}"
                )

            try:
                handler(action)
            except AEActionStopped:
                raise
            except Exception as exc:
                raise ExecutorError(
                    f"Action {index} "
                    f"({action.action!r}) failed: {exc}"
                ) from exc

            self.actions.check_stop()

    def execute_from(
        self,
        plan: EditingPlan,
        start_index: int = 0,
        *,
        on_progress: Callable[
            [int, EditingAction], None
        ]
        | None = None,
    ) -> int:
        """Execute actions starting from a given index.

        Returns the index of the last successfully completed action.
        Supports resuming after interruption.
        """
        if not isinstance(plan, EditingPlan):
            raise TypeError(
                "plan must be an EditingPlan."
            )

        if start_index < 0:
            raise ValueError(
                "start_index must not be negative."
            )

        if start_index >= len(plan.actions):
            return len(plan.actions) - 1

        last_completed = start_index - 1

        for index in range(
            start_index, len(plan.actions)
        ):
            action = plan.actions[index]
            self.actions.check_stop()

            handler = self.handlers.get(
                action.action
            )

            if handler is None:
                raise ExecutorError(
                    f"No execution handler is registered for "
                    f"action {index}: {action.action!r}"
                )

            try:
                handler(action)
            except AEActionStopped:
                raise
            except Exception as exc:
                raise ExecutorError(
                    f"Action {index} "
                    f"({action.action!r}) failed: {exc}"
                ) from exc

            last_completed = index

            if on_progress is not None:
                on_progress(index, action)

            self.actions.check_stop()

    def supported_actions(self) -> tuple[str, ...]:
        """Return registered action names."""

        return tuple(
            sorted(self.handlers)
        )