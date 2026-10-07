"""Visible mouse and keyboard control for After Effects.

This module provides a small, dependency-free Windows input layer
using the Win32 API. It does not generate or execute JSX.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Optional


class VisibleInputError(RuntimeError):
    """Raised when visible input cannot be performed."""


class VisibleInputController:
    """Control the Windows mouse and keyboard visibly."""

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_ABSOLUTE = 0x8000

    KEYEVENTF_KEYUP = 0x0002

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1

    def __init__(self) -> None:
        if __import__("os").name != "nt":
            raise VisibleInputError(
                "VisibleInputController currently supports Windows only."
            )

        self._user32 = ctypes.windll.user32

        self._screen_width = self._user32.GetSystemMetrics(0)
        self._screen_height = self._user32.GetSystemMetrics(1)

        if self._screen_width <= 0 or self._screen_height <= 0:
            raise VisibleInputError(
                "Unable to determine Windows screen dimensions."
            )

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return the current Windows screen dimensions."""
        return (
            self._screen_width,
            self._screen_height,
        )

    def move_mouse(
        self,
        x: int,
        y: int,
        *,
        duration: float = 0.0,
    ) -> None:
        """Move the visible mouse cursor to an absolute screen position."""

        self._validate_coordinates(x, y)

        if duration <= 0:
            self._send_mouse_move(x, y)
            return

        start_x, start_y = self.position()

        steps = max(
            1,
            int(duration * 60),
        )

        for step in range(1, steps + 1):
            progress = step / steps

            # Smooth ease-in/ease-out movement.
            eased = (
                progress * progress
                * (3.0 - 2.0 * progress)
            )

            current_x = round(
                start_x
                + (x - start_x) * eased
            )

            current_y = round(
                start_y
                + (y - start_y) * eased
            )

            self._send_mouse_move(
                current_x,
                current_y,
            )

            time.sleep(
                duration / steps
            )

    def position(self) -> tuple[int, int]:
        """Return the current mouse position."""

        point = wintypes.POINT()

        if not self._user32.GetCursorPos(
            ctypes.byref(point)
        ):
            raise VisibleInputError(
                "Unable to read the current mouse position."
            )

        return (
            int(point.x),
            int(point.y),
        )

    def left_click(
        self,
        *,
        clicks: int = 1,
        interval: float = 0.08,
    ) -> None:
        """Perform one or more visible left mouse clicks."""

        if clicks < 1:
            raise ValueError(
                "clicks must be at least 1."
            )

        for index in range(clicks):
            self._mouse_button(
                down=True,
                right=False,
            )

            self._mouse_button(
                down=False,
                right=False,
            )

            if index < clicks - 1:
                time.sleep(
                    max(0.0, interval)
                )

    def right_click(self) -> None:
        """Perform one visible right mouse click."""

        self._mouse_button(
            down=True,
            right=True,
        )

        self._mouse_button(
            down=False,
            right=True,
        )

    def key_down(
        self,
        virtual_key: int,
    ) -> None:
        """Press and hold a Windows virtual key."""

        self._keyboard(
            virtual_key,
            key_up=False,
        )

    def key_up(
        self,
        virtual_key: int,
    ) -> None:
        """Release a Windows virtual key."""

        self._keyboard(
            virtual_key,
            key_up=True,
        )

    def press(
        self,
        virtual_key: int,
        *,
        hold: float = 0.03,
    ) -> None:
        """Press and release a Windows virtual key."""

        self.key_down(
            virtual_key
        )

        try:
            if hold > 0:
                time.sleep(hold)
        finally:
            self.key_up(
                virtual_key
            )

    def hotkey(
        self,
        *virtual_keys: int,
        hold: float = 0.05,
    ) -> None:
        """Press several keys together, then release them."""

        if not virtual_keys:
            raise ValueError(
                "At least one virtual key is required."
            )

        pressed: list[int] = []

        try:
            for virtual_key in virtual_keys:
                self.key_down(
                    virtual_key
                )
                pressed.append(
                    virtual_key
                )

            if hold > 0:
                time.sleep(hold)

        finally:
            for virtual_key in reversed(
                pressed
            ):
                self.key_up(
                    virtual_key
                )

    def type_text(
        self,
        text: str,
        *,
        interval: float = 0.01,
    ) -> None:
        """Type ordinary text using Unicode keyboard input."""

        if not isinstance(text, str):
            raise TypeError(
                "text must be a string."
            )

        for character in text:
            self._type_character(
                character
            )

            if interval > 0:
                time.sleep(interval)

    def _send_mouse_move(
        self,
        x: int,
        y: int,
    ) -> None:
        normalized_x = round(
            x * 65535
            / max(
                1,
                self._screen_width - 1,
            )
        )

        normalized_y = round(
            y * 65535
            / max(
                1,
                self._screen_height - 1,
            )
        )

        self._user32.mouse_event(
            self.MOUSEEVENTF_MOVE
            | self.MOUSEEVENTF_ABSOLUTE,
            normalized_x,
            normalized_y,
            0,
            0,
        )

    def _mouse_button(
        self,
        *,
        down: bool,
        right: bool,
    ) -> None:
        if right:
            flag = (
                self.MOUSEEVENTF_RIGHTDOWN
                if down
                else self.MOUSEEVENTF_RIGHTUP
            )
        else:
            flag = (
                self.MOUSEEVENTF_LEFTDOWN
                if down
                else self.MOUSEEVENTF_LEFTUP
            )

        self._user32.mouse_event(
            flag,
            0,
            0,
            0,
            0,
        )

    def _keyboard(
        self,
        virtual_key: int,
        *,
        key_up: bool,
    ) -> None:
        flags = (
            self.KEYEVENTF_KEYUP
            if key_up
            else 0
        )

        self._user32.keybd_event(
            virtual_key,
            0,
            flags,
            0,
        )

    def _type_character(
        self,
        character: str,
    ) -> None:
        """Type one Unicode character through SendInput."""

        if not character:
            return

        if ord(character) > 0xFFFF:
            raise VisibleInputError(
                "Characters outside the Windows UTF-16 BMP "
                "are not supported by this text input method."
            )

        KEYEVENTF_UNICODE = 0x0004

        self._user32.keybd_event(
            0,
            ord(character),
            KEYEVENTF_UNICODE,
            0,
        )

        self._user32.keybd_event(
            0,
            ord(character),
            KEYEVENTF_UNICODE
            | self.KEYEVENTF_KEYUP,
            0,
        )

    def _validate_coordinates(
        self,
        x: int,
        y: int,
    ) -> None:
        if not isinstance(x, int):
            raise TypeError(
                "x must be an integer."
            )

        if not isinstance(y, int):
            raise TypeError(
                "y must be an integer."
            )

        if not (
            0 <= x < self._screen_width
        ):
            raise ValueError(
                f"x must be between 0 and "
                f"{self._screen_width - 1}."
            )

        if not (
            0 <= y < self._screen_height
        ):
            raise ValueError(
                f"y must be between 0 and "
                f"{self._screen_height - 1}."
            )