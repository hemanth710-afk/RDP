"""Thread-safe AI activity/status controller.

Manages the lifecycle of AI operations via a simple state machine
with listener support, safe stop semantics, and full thread safety.

Typical flow
─────────────
    controller = AIStatusController()
    controller.add_listener(my_callback)   # (old, new) → None
    controller.start()                     # → RUNNING
    # … worker checks controller.is_stop_requested() periodically …
    controller.mark_completed()            # → COMPLETED
    controller.reset()                     # → IDLE
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

from .states import AIState, InvalidStateTransition

logger = logging.getLogger(__name__)

# Type alias for listener callbacks.
StateChangeCallback = Callable[[AIState, AIState], None]


class AIStatusController:
    """Thread-safe AI activity controller.

    Public API
    ──────────
    start()            – Begin a new AI operation.
    request_stop()     – Ask the running operation to stop.
    is_stop_requested()– Poll whether stop was requested (for workers).
    mark_completed()   – Signal successful completion.
    mark_error(msg)    – Signal an error.
    mark_stopped()     – Confirm the operation has fully stopped.
    reset()            – Return to IDLE from any terminal state.
    state              – Property: current AIState (thread-safe read).
    error_message      – Property: last error message, if any.
    add_listener(cb)   – Register a (old_state, new_state) callback.
    remove_listener(cb)– Unregister a previously added callback.

    Thread Safety
    ─────────────
    All public methods and properties are guarded by a single
    reentrant-safe threading.Lock.  The stop signal uses a
    threading.Event so worker threads can poll or wait on it
    without holding the lock.

    Listener callbacks are invoked *outside* the lock to avoid
    deadlocks.  Exceptions raised inside listeners are caught
    and logged — they never corrupt the controller state.
    """

    # States from which start() is legal.
    _STARTABLE_STATES = frozenset({
        AIState.IDLE,
        AIState.STOPPED,
        AIState.COMPLETED,
        AIState.ERROR,
    })

    # States from which reset() is legal.
    _RESETTABLE_STATES = frozenset({
        AIState.IDLE,
        AIState.STOPPED,
        AIState.COMPLETED,
        AIState.ERROR,
    })

    # States from which mark_error() is legal.
    _ERROR_ALLOWED_STATES = frozenset({
        AIState.RUNNING,
        AIState.STOPPING,
    })

    def __init__(self) -> None:
        self._state: AIState = AIState.IDLE
        self._lock: threading.Lock = threading.Lock()
        self._stop_event: threading.Event = threading.Event()
        self._listeners: List[StateChangeCallback] = []
        self._error_message: Optional[str] = None

    # ── properties ──────────────────────────────────────────────

    @property
    def state(self) -> AIState:
        """Current state.  Thread-safe."""
        with self._lock:
            return self._state

    @property
    def error_message(self) -> Optional[str]:
        """Last error message set via :meth:`mark_error`, or *None*."""
        with self._lock:
            return self._error_message

    # ── lifecycle methods ───────────────────────────────────────

    def start(self) -> None:
        """Transition to RUNNING.

        Allowed from IDLE, STOPPED, COMPLETED, or ERROR.
        Clears any lingering stop signal and error message.

        Raises:
            InvalidStateTransition: if called from RUNNING or STOPPING.
        """
        with self._lock:
            if self._state not in self._STARTABLE_STATES:
                raise InvalidStateTransition(self._state, "start")
            old = self._state
            self._state = AIState.RUNNING
            self._stop_event.clear()
            self._error_message = None
        self._notify(old, AIState.RUNNING)

    def request_stop(self) -> None:
        """Request cancellation of the current operation.

        * Transitions RUNNING → STOPPING and sets the stop event.
        * **Safe to call repeatedly** — a no-op when not RUNNING.
        """
        with self._lock:
            if self._state != AIState.RUNNING:
                return  # idempotent / safe for repeated calls
            old = self._state
            self._state = AIState.STOPPING
            self._stop_event.set()
        self._notify(old, AIState.STOPPING)

    def is_stop_requested(self) -> bool:
        """Return *True* if :meth:`request_stop` has been called.

        Workers should poll this (or ``wait()`` on the underlying
        event) to learn when to shut down cooperatively.
        """
        return self._stop_event.is_set()

    def mark_completed(self) -> None:
        """Declare the operation completed successfully.

        Raises:
            InvalidStateTransition: if not RUNNING.
        """
        with self._lock:
            if self._state != AIState.RUNNING:
                raise InvalidStateTransition(self._state, "mark_completed")
            old = self._state
            self._state = AIState.COMPLETED
        self._notify(old, AIState.COMPLETED)

    def mark_error(self, message: Optional[str] = None) -> None:
        """Declare the operation failed.

        Args:
            message: human-readable error description (optional).

        Raises:
            InvalidStateTransition: if not RUNNING or STOPPING.
        """
        with self._lock:
            if self._state not in self._ERROR_ALLOWED_STATES:
                raise InvalidStateTransition(self._state, "mark_error")
            old = self._state
            self._state = AIState.ERROR
            self._error_message = message
            self._stop_event.clear()
        self._notify(old, AIState.ERROR)

    def mark_stopped(self) -> None:
        """Confirm the operation has fully stopped.

        Raises:
            InvalidStateTransition: if not STOPPING.
        """
        with self._lock:
            if self._state != AIState.STOPPING:
                raise InvalidStateTransition(self._state, "mark_stopped")
            old = self._state
            self._state = AIState.STOPPED
            self._stop_event.clear()
        self._notify(old, AIState.STOPPED)

    def reset(self) -> None:
        """Return to IDLE from any terminal state.

        A no-op when already IDLE.

        Raises:
            InvalidStateTransition: if RUNNING or STOPPING (must
                stop/complete/error first).
        """
        with self._lock:
            if self._state not in self._RESETTABLE_STATES:
                raise InvalidStateTransition(self._state, "reset")
            old = self._state
            if old == AIState.IDLE:
                return
            self._state = AIState.IDLE
            self._stop_event.clear()
            self._error_message = None
        self._notify(old, AIState.IDLE)

    # ── listener management ─────────────────────────────────────

    def add_listener(self, callback: StateChangeCallback) -> None:
        """Register *callback(old_state, new_state)* for transitions."""
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: StateChangeCallback) -> None:
        """Remove a previously registered listener (silent if absent)."""
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    # ── internal ────────────────────────────────────────────────

    def _notify(self, old: AIState, new: AIState) -> None:
        """Invoke every listener outside the lock.

        Exceptions are caught and logged so that a misbehaving
        listener can never corrupt the controller.
        """
        with self._lock:
            snapshot = list(self._listeners)
        for cb in snapshot:
            try:
                cb(old, new)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Listener %r raised %s during %s → %s: %s",
                    cb, type(exc).__name__, old.value, new.value, exc,
                )