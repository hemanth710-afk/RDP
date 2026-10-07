"""AI activity states and transition errors.

Defines the finite set of states the AI controller may occupy,
and the exception raised on illegal transitions.
"""

import enum


class AIState(enum.Enum):
    """Possible states of the AI activity controller.

    IDLE       – No AI operation is active.
    RUNNING    – The AI is actively working.
    STOPPING   – A stop has been requested; awaiting graceful shutdown.
    STOPPED    – The AI has fully stopped after a stop request.
    COMPLETED  – The AI operation finished successfully.
    ERROR      – The AI operation terminated due to an error.
    """

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class InvalidStateTransition(Exception):
    """Raised when a state-changing method is called from a disallowed state.

    Attributes:
        current_state     – The AIState at the time of the call.
        attempted_action  – Name of the method that was invoked.
    """

    def __init__(self, current_state: AIState, attempted_action: str,
                 message: str | None = None):
        self.current_state = current_state
        self.attempted_action = attempted_action
        if message is None:
            message = (
                f"Cannot perform '{attempted_action}' "
                f"while in state '{current_state.value}'"
            )
        super().__init__(message)