"""Sally face — Troko-inspired eyes-only Dynamic Island (from scratch)."""

from __future__ import annotations

import math
import tkinter as tk
from enum import Enum


class FaceExpression(str, Enum):
    IDLE = "idle"  # rest / waiting for wake
    LISTENING = "listening"
    THINKING = "thinking"
    HAPPY = "happy"


# Neon green accent + deep black island (Troko-adjacent look, original drawing)
_BG = "#07070a"
_ISLAND = "#101014"
_EYE = "#f5f5f7"
_ACCENT = "#39ff14"
_STATUS_FG = "#a3a3a3"
_STATUS_BG = "#07070a"


def _rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    radius: float,
    fill: str,
    tags: str | tuple[str, ...] = (),
) -> None:
    """Approximate a stadium / pill with a smooth polygon."""
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=24,
        fill=fill,
        outline="",
        tags=tags,
    )


def _egg_eye(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    w: float,
    h: float,
    *,
    fill: str = _EYE,
    rim: str | None = None,
    rim_pad: float = 4.0,
    tags: str | tuple[str, ...] = (),
) -> None:
    """Big soft oval eye — entirely white, optional neon rim around (never a pupil)."""
    if rim:
        canvas.create_oval(
            cx - w / 2 - rim_pad,
            cy - h / 2 - rim_pad,
            cx + w / 2 + rim_pad,
            cy + h / 2 + rim_pad,
            fill=rim,
            outline="",
            tags=tags,
        )
    canvas.create_oval(
        cx - w / 2,
        cy - h / 2,
        cx + w / 2,
        cy + h / 2,
        fill=fill,
        outline="",
        tags=tags,
    )


def _happy_crescent(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    w: float,
    h: float,
    *,
    fill: str,
    rim: str | None = None,
    tags: str | tuple[str, ...] = (),
) -> None:
    """Happy squint: white crescent, optional neon rim under the curve."""
    x1, y1 = cx - w / 2, cy - h / 2
    x2, y2 = cx + w / 2, cy + h / 2
    if rim:
        canvas.create_oval(
            x1 - 3,
            y1 - 3,
            x2 + 3,
            y2 + 3,
            fill=rim,
            outline="",
            tags=tags,
        )
        canvas.create_oval(
            x1 - 5,
            y1 - h * 0.9,
            x2 + 5,
            y2 - h * 0.2,
            fill=_ISLAND,
            outline="",
            tags=tags,
        )
    canvas.create_oval(x1, y1, x2, y2, fill=fill, outline="", tags=tags)
    canvas.create_oval(
        x1 - 2,
        y1 - h * 0.85,
        x2 + 2,
        y2 - h * 0.25,
        fill=_ISLAND,
        outline="",
        tags=tags,
    )


class FaceApp:
    """Thread-safe-ish face UI: call set_expression from audio thread via after()."""

    def __init__(self, title: str = "Sally Cibote") -> None:
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("520x380")
        self.root.resizable(False, False)
        self.root.configure(bg=_BG)
        self._expr = FaceExpression.IDLE
        self._status = tk.StringVar(value="aguardando: diga 'Slice'")
        self._phase = 0.0  # idle breath / listen pulse / thinking orbit
        self._anim_after: str | None = None

        self._canvas = tk.Canvas(
            self.root, width=520, height=310, highlightthickness=0, bg=_BG
        )
        self._canvas.pack(fill="both", expand=True)
        lbl = tk.Label(
            self.root,
            textvariable=self._status,
            font=("Segoe UI", 11),
            fg=_STATUS_FG,
            bg=_STATUS_BG,
            pady=12,
        )
        lbl.pack(fill="x")
        self._draw()
        self._tick()

    @property
    def expression(self) -> FaceExpression:
        return self._expr

    def set_expression(self, expr: FaceExpression, status: str | None = None) -> None:
        def _apply() -> None:
            self._expr = expr
            if status is not None:
                self._status.set(status)
            self._draw()

        try:
            self.root.after(0, _apply)
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        try:
            if self._anim_after is not None:
                self.root.after_cancel(self._anim_after)
                self._anim_after = None
            self.root.after(0, self.root.destroy)
        except tk.TclError:
            pass

    def _tick(self) -> None:
        """Subtle motion: idle breath, listen pulse, thinking dots orbit."""
        try:
            step = 0.12 if self._expr == FaceExpression.THINKING else 0.08
            self._phase = (self._phase + step) % (math.pi * 2)
            self._draw()
            self._anim_after = self.root.after(40, self._tick)
        except tk.TclError:
            self._anim_after = None

    def _draw_thinking_dots(self, c: tk.Canvas, mid_x: float, mid_y: float) -> None:
        """Three neon dots orbiting around the eye pair (eyes stay white)."""
        # Ellipse path around both eyes
        rx, ry = 64, 48
        for i in range(3):
            ang = self._phase + (i * (math.pi * 2 / 3))
            dx = math.cos(ang) * rx
            dy = math.sin(ang) * ry * 0.55
            # Soft size pulse so the lead dot feels like it's "passing"
            pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(ang + math.pi / 2))
            r = 4.5 * pulse
            c.create_oval(
                mid_x + dx - r,
                mid_y + dy - r,
                mid_x + dx + r,
                mid_y + dy + r,
                fill=_ACCENT,
                outline="",
                tags="think-dot",
            )

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        c.configure(bg=_BG)

        # Dynamic Island pill (taller for upright egg eyes)
        ix1, iy1, ix2, iy2 = 70, 72, 450, 248
        breath = 0.0
        if self._expr == FaceExpression.IDLE:
            breath = math.sin(self._phase) * 2.0
        elif self._expr == FaceExpression.LISTENING:
            breath = math.sin(self._phase * 1.6) * 2.5
        elif self._expr == FaceExpression.THINKING:
            breath = math.sin(self._phase * 0.9) * 1.2

        _rounded_rect(
            c,
            ix1,
            iy1 - breath,
            ix2,
            iy2 + breath,
            radius=62,
            fill=_ISLAND,
            tags="island",
        )

        mid_x = (ix1 + ix2) / 2
        mid_y = (iy1 + iy2) / 2 + breath * 0.12
        # ~1 finger gap between inner edges (was ~2); half-distance between centers
        gap = 38

        if self._expr == FaceExpression.IDLE:
            # Rest: vertical eggs, a bit wider, slightly drowsy
            eye_w, eye_h = 46, 60
            y_off = math.sin(self._phase) * 1.0
            for side in (-1, 1):
                _egg_eye(
                    c,
                    mid_x + side * gap,
                    mid_y + y_off,
                    eye_w,
                    eye_h,
                    fill=_EYE,
                    tags="eye",
                )

        elif self._expr == FaceExpression.LISTENING:
            # Attentive: wider upright eggs — plain white, no rim
            pulse = 1.0 + 0.05 * math.sin(self._phase * 2.0)
            eye_w, eye_h = 52 * pulse, 70 * pulse
            for side in (-1, 1):
                _egg_eye(
                    c,
                    mid_x + side * gap,
                    mid_y,
                    eye_w,
                    eye_h,
                    fill=_EYE,
                    tags="eye",
                )

        elif self._expr == FaceExpression.THINKING:
            # White upright eggs; three neon dots orbit around them
            eye_w, eye_h = 48, 64
            for side in (-1, 1):
                _egg_eye(
                    c,
                    mid_x + side * gap,
                    mid_y,
                    eye_w,
                    eye_h,
                    fill=_EYE,
                    tags="eye",
                )
            self._draw_thinking_dots(c, mid_x, mid_y)

        else:  # HAPPY
            # Vertical crescent squints — plain white, no rim + blush
            for side in (-1, 1):
                _happy_crescent(
                    c,
                    mid_x + side * gap,
                    mid_y + 4,
                    48,
                    54,
                    fill=_EYE,
                    tags="eye",
                )
            for side in (-1, 1):
                bx = mid_x + side * (gap + 34)
                by = mid_y + 32
                c.create_oval(bx - 7, by - 4, bx + 7, by + 4, fill="#ff6b8a", outline="")
                c.create_oval(bx - 3, by - 2, bx + 3, by + 2, fill="#ff8fab", outline="")

        # Tiny brand mark
        c.create_text(
            mid_x,
            iy2 + 36,
            text="SALLY",
            fill="#3f3f46",
            font=("Segoe UI", 10, "bold"),
        )
        c.create_oval(
            mid_x + 38, iy2 + 32, mid_x + 44, iy2 + 38, fill=_ACCENT, outline=""
        )
