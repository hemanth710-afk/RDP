"""Handlers that connect approved editing-plan actions to AE visible actions."""

from __future__ import annotations

from brain.editing_plan import EditingAction
from .actions import AEVisibleActions


class AEPlanHandlers:
    """Provide controlled handlers for approved editing actions."""

    def __init__(self, actions: AEVisibleActions) -> None:
        self.actions = actions

    def wait(self, action: EditingAction) -> None:
        """Execute a cooperative wait action."""

        seconds = action.parameters.get("seconds")

        if seconds is None:
            if (
                action.start_time is not None
                and action.end_time is not None
            ):
                seconds = action.end_time - action.start_time
            else:
                seconds = 0.0

        seconds = float(seconds)

        if seconds < 0:
            raise ValueError(
                "wait duration cannot be negative."
            )

        self.actions.wait(seconds)

    def create_project(self, action: EditingAction) -> None:
        """Create a new project through the visible AE interface."""

        del action

        self.actions.check_stop()

        # Ctrl+N opens the New Project workflow in After Effects.
        self.actions.hotkey(
            0x11,  # VK_CONTROL
            0x4E,  # VK_N
        )

        self.actions.wait(1.5)

        self.actions.check_stop()

    def handlers(self):
        """Return the currently supported plan handlers."""

        return {
            "wait": self.wait,
            "create_project": self.create_project,
        }