"""Animated electric AI activity indicator.

The UI uses only thin edge windows, leaving the center of the
desktop completely untouched. While the AI is running, blue
energy continuously moves around the four screen edges.

The bottom-right button requests a cooperative AI stop.
"""

from __future__ import annotations

import ctypes
import math
import random
import tkinter as tk
from typing import Optional

from .controller import AIStatusController
from .states import AIState


class AIStatusUI:
    """Electric animated screen-edge AI status indicator."""

    FRAME_MS = 30
    EDGE_THICKNESS = 24

    STOP_SIZE = 54
    STOP_MARGIN = 28

    def __init__(
        self,
        controller: AIStatusController,
        *,
        root: Optional[tk.Tk] = None,
    ) -> None:
        self._controller = controller
        self._root = root if root is not None else tk.Tk()

        self._root.withdraw()

        self._screen_width = self._root.winfo_screenwidth()
        self._screen_height = self._root.winfo_screenheight()

        self._edge_windows: list[tk.Toplevel] = []
        self._edge_canvases: list[tk.Canvas] = []

        self._stop_window: Optional[tk.Toplevel] = None
        self._stop_canvas: Optional[tk.Canvas] = None

        self._running = False
        self._after_id: Optional[str] = None

        self._phase = 0.0
        self._random = random.Random(9137)

        self._create_edge_windows()

        self._controller.add_listener(
            self._on_state_change
        )

        self._apply_state(
            self._controller.state
        )

    @property
    def root(self) -> tk.Tk:
        return self._root

    # ============================================================
    # EDGE WINDOWS
    # ============================================================

    def _create_edge_windows(self) -> None:
        definitions = [
            (
                0,
                0,
                self._screen_width,
                self.EDGE_THICKNESS,
                "top",
            ),
            (
                0,
                self._screen_height - self.EDGE_THICKNESS,
                self._screen_width,
                self.EDGE_THICKNESS,
                "bottom",
            ),
            (
                0,
                0,
                self.EDGE_THICKNESS,
                self._screen_height,
                "left",
            ),
            (
                self._screen_width - self.EDGE_THICKNESS,
                0,
                self.EDGE_THICKNESS,
                self._screen_height,
                "right",
            ),
        ]

        for x, y, width, height, side in definitions:
            window = tk.Toplevel(self._root)

            window.overrideredirect(True)
            window.attributes("-topmost", True)

            window.configure(
                bg="#020817"
            )

            window.geometry(
                f"{width}x{height}+{x}+{y}"
            )

            canvas = tk.Canvas(
                window,
                width=width,
                height=height,
                bg="#020817",
                highlightthickness=0,
                bd=0,
            )

            canvas.pack(
                fill="both",
                expand=True,
            )

            window._ai_side = side

            self._edge_windows.append(window)
            self._edge_canvases.append(canvas)

            self._make_click_through(
                window
            )

            window.withdraw()

    def _make_click_through(
        self,
        window: tk.Toplevel,
    ) -> None:
        """Make edge windows ignore mouse clicks on Windows."""

        try:
            window.update_idletasks()

            hwnd = window.winfo_id()

            user32 = ctypes.windll.user32

            GWL_EXSTYLE = -20

            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000

            style = user32.GetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
            )

            style |= (
                WS_EX_TRANSPARENT
                | WS_EX_TOOLWINDOW
                | WS_EX_NOACTIVATE
            )

            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style,
            )

        except (
            AttributeError,
            OSError,
            tk.TclError,
        ):
            pass

    # ============================================================
    # STATE
    # ============================================================

    def _on_state_change(
        self,
        _old_state: AIState,
        new_state: AIState,
    ) -> None:
        try:
            self._root.after(
                0,
                lambda: self._apply_state(
                    new_state
                ),
            )
        except tk.TclError:
            pass

    def _apply_state(
        self,
        state: AIState,
    ) -> None:
        if state == AIState.RUNNING:
            self.show()
            self._start_animation()
        else:
            self.hide()

    # ============================================================
    # VISIBILITY
    # ============================================================

    def show(self) -> None:
        try:
            for window in self._edge_windows:
                window.deiconify()
                window.lift()

            self._show_stop_button()

        except tk.TclError:
            pass

    def hide(self) -> None:
        self._stop_animation()

        for window in self._edge_windows:
            try:
                window.withdraw()
            except tk.TclError:
                pass

        self._hide_stop_button()

    def close(self) -> None:
        self._stop_animation()

        self._controller.remove_listener(
            self._on_state_change
        )

        self._hide_stop_button()

        for window in self._edge_windows:
            try:
                window.destroy()
            except tk.TclError:
                pass

        self._edge_windows.clear()
        self._edge_canvases.clear()

        try:
            self._root.destroy()
        except tk.TclError:
            pass

    # ============================================================
    # ANIMATION
    # ============================================================

    def _start_animation(self) -> None:
        if self._running:
            return

        self._running = True
        self._phase = 0.0

        self._animate()

    def _stop_animation(self) -> None:
        self._running = False

        if self._after_id is not None:
            try:
                self._root.after_cancel(
                    self._after_id
                )
            except tk.TclError:
                pass

            self._after_id = None

    def _animate(self) -> None:
        if not self._running:
            return

        self._phase += 0.075

        if self._phase >= math.tau:
            self._phase -= math.tau

        self._draw_edges()
        self._draw_stop_button()

        try:
            self._after_id = self._root.after(
                self.FRAME_MS,
                self._animate,
            )
        except tk.TclError:
            self._after_id = None

    # ============================================================
    # ELECTRIC EDGE EFFECT
    # ============================================================

    def _draw_edges(self) -> None:
        for index, canvas in enumerate(
            self._edge_canvases
        ):
            try:
                canvas.delete("all")

                side = self._edge_windows[
                    index
                ]._ai_side

                if side in (
                    "top",
                    "bottom",
                ):
                    self._draw_horizontal_energy(
                        canvas,
                        side,
                    )
                else:
                    self._draw_vertical_energy(
                        canvas,
                        side,
                    )

            except tk.TclError:
                pass

    def _energy_intensity(
        self,
        position: float,
    ) -> float:
        wave = (
            math.sin(
                self._phase * 2.1
                + position * 0.045
            )
            + 1.0
        ) / 2.0

        pulse = (
            math.sin(
                self._phase * 1.4
            )
            + 1.0
        ) / 2.0

        return (
            0.45
            + wave * 0.35
            + pulse * 0.20
        )

    def _draw_horizontal_energy(
        self,
        canvas: tk.Canvas,
        side: str,
    ) -> None:
        width = canvas.winfo_width()

        if width <= 1:
            return

        center_y = (
            self.EDGE_THICKNESS / 2
        )

        # Deep blue base.
        canvas.create_rectangle(
            0,
            0,
            width,
            self.EDGE_THICKNESS,
            fill="#020817",
            outline="",
        )

        points: list[float] = []

        step = 12

        for x in range(
            0,
            width + step,
            step,
        ):
            intensity = self._energy_intensity(
                float(x)
            )

            wave_a = math.sin(
                self._phase * 4.0
                + x * 0.025
            )

            wave_b = math.sin(
                self._phase * 7.0
                + x * 0.061
            )

            distortion = (
                wave_a * 2.4
                + wave_b * 1.2
            ) * intensity

            if side == "bottom":
                y = (
                    center_y
                    - distortion
                )
            else:
                y = (
                    center_y
                    + distortion
                )

            points.extend(
                [x, y]
            )

        # Outer electric glow.
        for glow_width, offset in (
            (10, 0),
            (7, 0),
            (4, 0),
        ):
            shifted = []

            for i in range(
                0,
                len(points),
                2,
            ):
                shifted.extend(
                    [
                        points[i],
                        points[i + 1],
                    ]
                )

            canvas.create_line(
                shifted,
                fill=(
                    "#0b3f91"
                    if glow_width == 10
                    else "#0877e8"
                    if glow_width == 7
                    else "#29a7ff"
                ),
                width=glow_width,
                smooth=True,
                splinesteps=3,
            )

        # Fast moving electric streaks.
        for streak in range(5):
            travel = (
                self._phase * (
                    0.9
                    + streak * 0.13
                )
                + streak * 1.7
            ) % 1.0

            x = int(
                width * travel
            )

            length = (
                80
                + streak * 35
            )

            canvas.create_line(
                x - length,
                center_y,
                x,
                center_y,
                fill="#70d0ff",
                width=2,
            )

        # Tiny energy sparks.
        for spark in range(18):
            seed = (
                spark * 83
            )

            travel = (
                self._phase * (
                    0.7
                    + spark * 0.017
                )
                + seed
            ) % 1.0

            x = int(
                width * travel
            )

            y = (
                center_y
                + math.sin(
                    self._phase * 5
                    + spark
                ) * 5
            )

            radius = (
                1
                + (
                    spark % 2
                )
            )

            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#8edcff",
                outline="",
            )

    def _draw_vertical_energy(
        self,
        canvas: tk.Canvas,
        side: str,
    ) -> None:
        height = canvas.winfo_height()

        if height <= 1:
            return

        center_x = (
            self.EDGE_THICKNESS / 2
        )

        points: list[float] = []

        step = 12

        for y in range(
            0,
            height + step,
            step,
        ):
            intensity = self._energy_intensity(
                float(y)
            )

            wave_a = math.sin(
                self._phase * 4.0
                + y * 0.025
            )

            wave_b = math.sin(
                self._phase * 7.0
                + y * 0.061
            )

            distortion = (
                wave_a * 2.4
                + wave_b * 1.2
            ) * intensity

            if side == "right":
                x = (
                    center_x
                    - distortion
                )
            else:
                x = (
                    center_x
                    + distortion
                )

            points.extend(
                [x, y]
            )

        for glow_width, glow_color in (
            (10, "#0b3f91"),
            (7, "#0877e8"),
            (4, "#29a7ff"),
        ):
            canvas.create_line(
                points,
                fill=glow_color,
                width=glow_width,
                smooth=True,
                splinesteps=3,
            )

        # Moving streaks.
        for streak in range(5):
            travel = (
                self._phase * (
                    0.9
                    + streak * 0.13
                )
                + streak * 1.7
            ) % 1.0

            y = int(
                height * travel
            )

            length = (
                80
                + streak * 35
            )

            canvas.create_line(
                center_x,
                y - length,
                center_x,
                y,
                fill="#70d0ff",
                width=2,
            )

        # Sparks.
        for spark in range(18):
            seed = (
                spark * 83
            )

            travel = (
                self._phase * (
                    0.7
                    + spark * 0.017
                )
                + seed
            ) % 1.0

            y = int(
                height * travel
            )

            x = (
                center_x
                + math.sin(
                    self._phase * 5
                    + spark
                ) * 5
            )

            radius = (
                1
                + (
                    spark % 2
                )
            )

            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#8edcff",
                outline="",
            )

    # ============================================================
    # STOP BUTTON
    # ============================================================

    def _show_stop_button(self) -> None:
        if self._stop_window is not None:
            try:
                self._stop_window.deiconify()
                self._stop_window.lift()
                return
            except tk.TclError:
                self._stop_window = None

        try:
            window = tk.Toplevel(
                self._root
            )

            self._stop_window = window

            window.overrideredirect(True)
            window.attributes(
                "-topmost",
                True,
            )

            window.configure(
                bg="#010101"
            )

            try:
                window.attributes(
                    "-transparentcolor",
                    "#010101",
                )
            except tk.TclError:
                pass

            size = self.STOP_SIZE + 20

            window.geometry(
                f"{size}x{size}"
            )

            canvas = tk.Canvas(
                window,
                width=size,
                height=size,
                bg="#010101",
                highlightthickness=0,
                bd=0,
            )

            canvas.pack()

            self._stop_canvas = canvas

            canvas.bind(
                "<Button-1>",
                self._on_stop_click,
            )

            canvas.bind(
                "<Enter>",
                lambda _event: canvas.configure(
                    cursor="hand2"
                ),
            )

            canvas.bind(
                "<Leave>",
                lambda _event: canvas.configure(
                    cursor=""
                ),
            )

            self._position_stop_button()

            window.deiconify()
            window.lift()

        except tk.TclError:
            self._stop_window = None
            self._stop_canvas = None

    def _position_stop_button(self) -> None:
        if self._stop_window is None:
            return

        try:
            size = (
                self.STOP_SIZE + 20
            )

            x = (
                self._screen_width
                - self.STOP_MARGIN
                - size
            )

            y = (
                self._screen_height
                - self.STOP_MARGIN
                - size
            )

            self._stop_window.geometry(
                f"{size}x{size}+{x}+{y}"
            )

        except tk.TclError:
            pass

    def _draw_stop_button(self) -> None:
        if self._stop_canvas is None:
            return

        try:
            self._stop_canvas.delete(
                "all"
            )

            size = (
                self.STOP_SIZE + 20
            )

            center = size / 2

            pulse = (
                math.sin(self._phase)
                + 1
            ) / 2

            outer = (
                self.STOP_SIZE / 2
                + 6
                + int(4 * pulse)
            )

            self._stop_canvas.create_oval(
                center - outer,
                center - outer,
                center + outer,
                center + outer,
                fill="#061b38",
                outline="#1679df",
                width=2,
            )

            radius = (
                self.STOP_SIZE / 2
            )

            self._stop_canvas.create_oval(
                center - radius,
                center - radius,
                center + radius,
                center + radius,
                fill="#0877e8",
                outline="#72c5ff",
                width=2,
            )

            square = 16

            self._stop_canvas.create_rectangle(
                center - square / 2,
                center - square / 2,
                center + square / 2,
                center + square / 2,
                fill="#ffffff",
                outline="",
            )

        except tk.TclError:
            pass

    def _hide_stop_button(self) -> None:
        if self._stop_window is None:
            return

        try:
            self._stop_window.withdraw()
        except tk.TclError:
            pass

    def _on_stop_click(
        self,
        _event: tk.Event,
    ) -> None:
        """Request cooperative AI shutdown."""

        self._controller.request_stop()