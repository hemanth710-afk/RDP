"""AI editing session coordinator.

Connects the AI activity service with the visible After Effects 2022
controller.

This module does not generate or execute JSX.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from ai_status.service import AIActivityService

from .controller import AEVisualController, AEVisualError


class AEVisualSessionError(RuntimeError):
    """Raised when a visible AE editing session cannot be started."""


class AEVisualSession:
    """Coordinate an AI editing session in visible After Effects."""

    def __init__(
        self,
        ae_controller: AEVisualController,
        activity_service: AIActivityService,
        *,
        startup_timeout: float = 30.0,
        poll_interval: float = 0.10,
    ) -> None:
        if startup_timeout <= 0:
            raise ValueError(
                "startup_timeout must be greater than zero."
            )

        if poll_interval <= 0:
            raise ValueError(
                "poll_interval must be greater than zero."
            )

        self.ae_controller = ae_controller
        self.activity_service = activity_service
        self.startup_timeout = startup_timeout
        self.poll_interval = poll_interval

        self._session_lock = threading.RLock()
        self._stop_event = threading.Event()

        self._worker_thread: Optional[threading.Thread] = None
        self._active = False

    @property
    def is_active(self) -> bool:
        """Return True while a visible editing session is active."""
        with self._session_lock:
            return self._active

    @property
    def is_stop_requested(self) -> bool:
        """Return True when the session has received a stop request."""
        return self._stop_event.is_set()

    def start(self) -> None:
        """Start the visible After Effects AI session.

        The session:

        1. Starts the AI activity state.
        2. Launches After Effects visibly.
        3. Waits for the process.
        4. Brings After Effects to the foreground.
        5. Waits for future visible editing work.
        """

        with self._session_lock:
            if self._active:
                raise AEVisualSessionError(
                    "An AE visual editing session is already active."
                )

            self._active = True
            self._stop_event.clear()

        try:
            self.activity_service.start()

            if self.activity_service.controller.is_stop_requested():
                self._stop_event.set()

            self.ae_controller.launch()

            self.ae_controller.wait_for_window(
                timeout=self.startup_timeout,
                poll_interval=self.poll_interval,
            )

            if self._should_stop():
                self._finish_stopped()
                return

            self.ae_controller.focus()

            self._worker_thread = threading.Thread(
                target=self._session_worker,
                name="AI-EDITOR-AE-Visual-Session",
                daemon=True,
            )

            self._worker_thread.start()

        except Exception as exc:
            self._handle_start_failure(exc)

            if isinstance(exc, AEVisualError):
                raise

            raise AEVisualSessionError(
                f"Unable to start AE visual session: {exc}"
            ) from exc

    def request_stop(self) -> None:
        """Request a cooperative stop of the editing session."""

        self._stop_event.set()

        self.activity_service.stop()

    def wait(self, timeout: Optional[float] = None) -> None:
        """Wait for the session worker to finish."""

        worker = self._worker_thread

        if worker is None:
            return

        worker.join(timeout)

    def close(self) -> None:
        """Request a stop and wait briefly for session shutdown."""

        if not self.is_active:
            return

        self.request_stop()

        self.wait(
            timeout=5.0
        )

    def _session_worker(self) -> None:
        """Run the cooperative session lifecycle."""

        try:
            while not self._should_stop():
                if not self.ae_controller.is_running:
                    self.activity_service.error(
                        "After Effects exited during the AI editing session."
                    )
                    return

                time.sleep(
                    self.poll_interval
                )

            self._finish_stopped()

        except Exception as exc:
            try:
                self.activity_service.error(
                    str(exc)
                )
            except Exception:
                pass

        finally:
            with self._session_lock:
                self._active = False

    def _should_stop(self) -> bool:
        """Return True if either stop mechanism has been triggered."""

        if self._stop_event.is_set():
            return True

        return self.activity_service.controller.is_stop_requested()

    def _finish_stopped(self) -> None:
        """Complete the cooperative stop transition."""

        try:
            if self.activity_service.controller.state.value == "stopping":
                self.activity_service.stopped()
        finally:
            with self._session_lock:
                self._active = False

    def _handle_start_failure(
        self,
        exc: Exception,
    ) -> None:
        """Convert startup failure into an AI error state."""

        self._stop_event.set()

        try:
            state = (
                self.activity_service.controller.state.value
            )

            if state in (
                "running",
                "stopping",
            ):
                self.activity_service.error(
                    str(exc)
                )

        except Exception:
            pass

        with self._session_lock:
            self._active = False