"""Controlled visible actions for the AI EDITOR AE workflow.

This layer wraps the low-level Windows input controller and makes
actions cooperative with the AI stop mechanism.

No JSX is generated or executed here.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .input_controller import VisibleInputController


class AEActionStopped(RuntimeError):
    """Raised when a visible action is interrupted by Stop."""


class AEActionError(RuntimeError):
    """Raised when a visible AE action cannot be performed."""


class AEVisibleActions:
    """Safe, named visible actions used by an AI editing workflow."""

    def __init__(
        self,
        input_controller: VisibleInputController,
        *,
        stop_checker: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.input = input_controller
        self._stop_checker = stop_checker

    def stop_requested(self) -> bool:
        """Return whether the current editing operation should stop."""

        if self._stop_checker is None:
            return False

        return bool(
            self._stop_checker()
        )

    def check_stop(self) -> None:
        """Raise AEActionStopped when Stop has been requested."""

        if self.stop_requested():
            raise AEActionStopped(
                "Visible AE editing was stopped by the user."
            )

    def move_to(
        self,
        x: int,
        y: int,
        *,
        duration: float = 0.20,
    ) -> None:
        """Move the visible mouse cursor."""

        self.check_stop()

        self.input.move_mouse(
            x,
            y,
            duration=duration,
        )

        self.check_stop()

    def click(
        self,
        x: int,
        y: int,
        *,
        duration: float = 0.20,
    ) -> None:
        """Move to a screen coordinate and left-click."""

        self.move_to(
            x,
            y,
            duration=duration,
        )

        self.check_stop()

        self.input.left_click()

        self.check_stop()

    def double_click(
        self,
        x: int,
        y: int,
        *,
        duration: float = 0.20,
    ) -> None:
        """Move to a screen coordinate and double-click."""

        self.move_to(
            x,
            y,
            duration=duration,
        )

        self.check_stop()

        self.input.left_click(
            clicks=2,
            interval=0.10,
        )

        self.check_stop()

    def right_click(
        self,
        x: int,
        y: int,
        *,
        duration: float = 0.20,
    ) -> None:
        """Move to a screen coordinate and right-click."""

        self.move_to(
            x,
            y,
            duration=duration,
        )

        self.check_stop()

        self.input.right_click()

        self.check_stop()

    def press(
        self,
        key: int,
        *,
        hold: float = 0.03,
    ) -> None:
        """Press one virtual key."""

        self.check_stop()

        self.input.press(
            key,
            hold=hold,
        )

        self.check_stop()

    def hotkey(
        self,
        *keys: int,
        hold: float = 0.05,
    ) -> None:
        """Press a keyboard shortcut."""

        self.check_stop()

        self.input.hotkey(
            *keys,
            hold=hold,
        )

        self.check_stop()

    def type_text(
        self,
        text: str,
        *,
        interval: float = 0.015,
    ) -> None:
        """Type text visibly into the active AE field."""

        if not isinstance(text, str):
            raise TypeError(
                "text must be a string."
            )

        self.check_stop()

        for character in text:
            self.check_stop()

            self.input.type_text(
                character,
                interval=0.0,
            )

            if interval > 0:
                time.sleep(interval)

        self.check_stop()

    def wait(
        self,
        seconds: float,
    ) -> None:
        """Wait while continuously checking Stop."""

        if seconds < 0:
            raise ValueError(
                "seconds cannot be negative."
            )

        deadline = (
            time.monotonic()
            + seconds
        )

        while True:
            self.check_stop()

            remaining = (
                deadline
                - time.monotonic()
            )

            if remaining <= 0:
                break

            time.sleep(
                min(
                    0.05,
                    remaining,
                )
            )