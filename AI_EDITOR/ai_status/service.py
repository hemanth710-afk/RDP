"""Application-level AI activity service."""

from __future__ import annotations

from .controller import AIStatusController


class AIActivityService:
    """Small application-facing wrapper around AIStatusController."""

    def __init__(self, controller: AIStatusController | None = None):
        self.controller = controller or AIStatusController()

    @property
    def is_running(self) -> bool:
        """Return True while the AI is actively working."""
        return self.controller.state.value == "running"

    def start(self) -> None:
        """Tell the status system that AI work has started."""
        self.controller.start()

    def stop(self) -> None:
        """Request the AI worker to stop."""
        self.controller.request_stop()

    def completed(self) -> None:
        """Tell the status system that AI work completed."""
        self.controller.mark_completed()

    def stopped(self) -> None:
        """Confirm that the AI worker has stopped."""
        self.controller.mark_stopped()

    def error(self, message: str | None = None) -> None:
        """Tell the status system that AI work failed."""
        self.controller.mark_error(message)

    def reset(self) -> None:
        """Return the status system to IDLE."""
        self.controller.reset()