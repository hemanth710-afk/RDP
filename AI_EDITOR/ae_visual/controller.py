"""Visible After Effects 2022 controller.

This module launches and focuses After Effects 2022 without using JSX.
It is intentionally separate from the existing ae_automation JSX engine.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional


class AEVisualError(RuntimeError):
    """Raised when visible After Effects control cannot be performed."""


class AEVisualController:
    """Launch and focus a visible After Effects 2022 instance."""

    ENVIRONMENT_VARIABLE = "AI_EDITOR_AFTER_EFFECTS_2022_PATH"

    def __init__(
        self,
        executable_path: Optional[str] = None,
    ) -> None:
        configured_path = (
            executable_path
            if executable_path is not None
            else os.environ.get(
                self.ENVIRONMENT_VARIABLE
            )
        )

        if not configured_path:
            raise AEVisualError(
                "After Effects 2022 executable path is not configured. "
                f"Set {self.ENVIRONMENT_VARIABLE} or provide executable_path."
            )

        self.executable_path = Path(
            configured_path
        ).expanduser()

        if not self.executable_path.exists():
            raise AEVisualError(
                "After Effects 2022 executable does not exist: "
                f"{self.executable_path}"
            )

        if not self.executable_path.is_file():
            raise AEVisualError(
                "After Effects 2022 executable path is not a file: "
                f"{self.executable_path}"
            )

        self.process: Optional[subprocess.Popen] = None

    @property
    def is_running(self) -> bool:
        """Return True when the launched AE process is still alive."""

        if self.process is None:
            return False

        return self.process.poll() is None

    def launch(self) -> subprocess.Popen:
        """Launch After Effects 2022 visibly."""

        try:
            self.process = subprocess.Popen(
                [str(self.executable_path)],
                shell=False,
            )
        except OSError as exc:
            raise AEVisualError(
                f"Unable to launch After Effects 2022: {exc}"
            ) from exc

        return self.process

    def wait_for_window(
        self,
        timeout: float = 30.0,
        poll_interval: float = 0.25,
    ) -> None:
        """Wait for the AE process to remain alive.

        This does not automate AE yet. It simply gives AE time to open
        before a future visible-interaction layer begins.
        """

        if self.process is None:
            raise AEVisualError(
                "After Effects has not been launched."
            )

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AEVisualError(
                    "After Effects exited before becoming ready."
                )

            time.sleep(poll_interval)

    def focus(self) -> bool:
        """Bring the After Effects window to the foreground on Windows."""

        if os.name != "nt":
            return False

        if self.process is None:
            raise AEVisualError(
                "After Effects has not been launched."
            )

        if self.process.poll() is not None:
            return False

        try:
            import ctypes

            user32 = ctypes.windll.user32

            found = []

            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )

            def callback(hwnd, _lparam):
                process_id = ctypes.c_ulong()

                user32.GetWindowThreadProcessId(
                    hwnd,
                    ctypes.byref(process_id),
                )

                if process_id.value == self.process.pid:
                    if user32.IsWindowVisible(hwnd):
                        found.append(hwnd)
                        return False

                return True

            user32.EnumWindows(
                EnumWindowsProc(callback),
                0,
            )

            if not found:
                return False

            hwnd = found[0]

            SW_RESTORE = 9

            user32.ShowWindow(
                hwnd,
                SW_RESTORE,
            )

            user32.SetForegroundWindow(
                hwnd
            )

            return True

        except (
            AttributeError,
            OSError,
            ctypes.ArgumentError,
        ):
            return False

    def stop_process(self) -> None:
        """Request termination of the launched AE process.

        This is intentionally separate from the AI stop request. The
        normal Stop button should first request the AI worker to stop;
        force-closing AE should only be used by an explicit shutdown
        policy.
        """

        if self.process is None:
            return

        if self.process.poll() is None:
            self.process.terminate()

        self.process = None