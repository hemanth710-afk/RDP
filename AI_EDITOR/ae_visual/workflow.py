"""Visible AI editing workflow.

Coordinates AI status, the visible After Effects session, and
controlled mouse/keyboard actions.

No JSX is generated or executed here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable

from ai_status.service import AIActivityService

from .actions import AEActionStopped, AEVisibleActions
from .session import AEVisualSession


class AIEditingWorkflowError(RuntimeError):
    """Raised when an AI editing workflow fails."""


@dataclass(frozen=True)
class EditingAction:
    """A single visible editing operation."""

    name: str
    action: Callable[[AEVisibleActions], None]
    duration: float = 0.0


class AIEditingWorkflow:
    """Run an AI-generated editing plan visibly in After Effects."""

    def __init__(
        self,
        session: AEVisualSession,
        activity_service: AIActivityService,
        actions: AEVisibleActions,
    ) -> None:
        self.session = session
        self.activity_service = activity_service
        self.actions = actions

    @property
    def is_running(self) -> bool:
        """Return True while the workflow is active."""
        return self.session.is_active

    @property
    def stop_requested(self) -> bool:
        """Return True when the user has requested Stop."""
        return (
            self.session.is_stop_requested
            or self.activity_service.controller.is_stop_requested()
        )

    def run(
        self,
        editing_actions: Iterable[EditingAction],
    ) -> None:
        """Run visible editing actions in After Effects."""

        action_list = list(editing_actions)

        if not action_list:
            raise ValueError(
                "At least one editing action is required."
            )

        if self.is_running:
            raise AIEditingWorkflowError(
                "An AI editing workflow is already running."
            )

        try:
            self.session.start()

            for editing_action in action_list:
                self._check_stop()

                if not editing_action.name.strip():
                    raise ValueError(
                        "Editing action name cannot be empty."
                    )

                if editing_action.duration < 0:
                    raise ValueError(
                        "Editing action duration cannot be negative."
                    )

                editing_action.action(
                    self.actions
                )

                self._wait_with_stop(
                    editing_action.duration
                )

                self._check_stop()

            if (
                self.activity_service.controller.state.value
                == "running"
            ):
                self.activity_service.completed()

        except AEActionStopped:
            self._complete_stop()

        except _WorkflowStopped:
            self._complete_stop()

        except Exception as exc:
            self._handle_error(exc)

            raise AIEditingWorkflowError(
                f"AI editing workflow failed: {exc}"
            ) from exc

        finally:
            self.session.wait(
                timeout=5.0
            )

    def stop(self) -> None:
        """Request a cooperative workflow stop."""

        self.session.request_stop()

    def _check_stop(self) -> None:
        if self.stop_requested:
            raise _WorkflowStopped()

    def _wait_with_stop(
        self,
        duration: float,
    ) -> None:
        """Wait while continuously checking the Stop state."""

        if duration <= 0:
            return

        deadline = (
            time.monotonic()
            + duration
        )

        while True:
            self._check_stop()

            remaining = (
                deadline
                - time.monotonic()
            )

            if remaining <= 0:
                return

            time.sleep(
                min(
                    0.05,
                    remaining,
                )
            )

    def _complete_stop(self) -> None:
        """Complete the controller's STOPPING → STOPPED transition."""

        state = (
            self.activity_service.controller.state.value
        )

        if state == "stopping":
            self.activity_service.stopped()

    def _handle_error(
        self,
        exc: Exception,
    ) -> None:
        """Move the activity controller into ERROR state."""

        state = (
            self.activity_service.controller.state.value
        )

        if state in (
            "running",
            "stopping",
        ):
            try:
                self.activity_service.error(
                    str(exc)
                )
            except Exception:
                pass


class _WorkflowStopped(Exception):
    """Internal cooperative workflow-stop signal."""