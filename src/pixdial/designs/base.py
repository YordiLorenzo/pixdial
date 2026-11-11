"""The Design base class, and the small helpers designs share."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import ClassVar

import numpy as np
from PIL import Image

from ..readings import Snapshot, TrailSpec
from .colour import RGB, Scale, Theme, current, solid
from .frame import DOT, Frame, Pixels, Still, with_text
from .geometry import MID, kit
from .motion import F64

# Limits where a reading brings none (the hardware reports none and the config sets none): neutral values in °C, W
# and A (a 12V-2x6 or 12VHPWR pin is rated 9.5 A)
DEFAULT_MAX = {"cpu_c": 100.0, "gpu_c": 90.0, "psu_c": 70.0, "gpu_w": 450.0, "psu_w": 1000.0, "pins": 9.5}


class Design:
    """One look for a round 400 x 400 panel.

    update() takes a snapshot of the readings and returns (still key, moving key). A new still key redraws the still
    part (still(): everything that changes only with the readings, with its blurred glow, a few ms); a new moving key
    repaints only the moving part (moving(): a comet, a sweep, painted over a copy of the still part, about 1 ms), at
    up to fps frames a second. A moving key of None means nothing animates now.
    """

    name: ClassVar[str]
    shows: ClassVar[str]  # what it shows, one line
    about: ClassVar[str] = ""  # how it looks, for the gallery
    fps: ClassVar[int] = 0
    under_text: ClassVar[bool] = False  # whether moving() paints where the text is (then text goes over every frame)
    trails: ClassVar[tuple[TrailSpec, ...]] = ()  # readings whose past it draws
    reads: ClassVar[tuple[str, ...]] = ()  # the readings it shows (`doctor --share` lists those no source gives)
    needs: ClassVar[tuple[str, ...]] = ()  # those it is mostly dashes without: while no source gives one of them,
    # the default rotation and layout leave it out
    previews: ClassVar[tuple[str, ...]] = ("busy", "idle")  # the demo states the gallery shows it in
    LABEL_Y, LINE_Y, FOOT_Y = 104, 292, 352  # the label over a ring design's number, the line under it, the foot

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        self.kit, self.theme = kit(scale), theme

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        raise NotImplementedError

    def still(self) -> Still:
        raise NotImplementedError

    def moving(self, px: Pixels, now: float) -> None:
        """Paints the moving part over px, a copy of the still part."""

    def animating(self, now: float) -> int:
        """A moving key that changes fps times a second."""
        return int(now * self.fps)

    def render(self, now: float) -> Image.Image:
        """The whole frame at once (the runtime keeps the still part and repaints only the moving one)."""
        px, text = self.still()
        self.moving(px, now)
        return with_text(px, text)

    def frame(self, tint: Sequence[float] | None = None, strength: float = 0.08) -> Frame:
        """A frame lit faintly from the middle in tint; none (a calm frame) while the reading is missing."""
        return Frame(self.kit, self.theme, tint, strength)

    def tone(self, scale: Scale, value: float) -> RGB:
        """A single value's colour on its scale."""
        r, g, b = (float(c) for c in solid(self.theme, scale.level(value)))
        return r, g, b

    def colour(self, scale: Scale, value: float | None) -> RGB | None:
        """A single value's colour on its scale; None while it is missing."""
        return None if value is None else self.tone(scale, value)

    def label(self, f: Frame, s: str, y: float | None = None, spacing: float = 6) -> None:
        f.write((MID, y or self.LABEL_Y), s, "Bold", 28, self.theme.dim, spacing=spacing, fit=170)

    def line(
        self,
        f: Frame,
        text: str,
        y: float | None = None,
        size: float = 34,
        rgb: Sequence[float] | None = None,
        fit: float = 150,
        spacing: float = 0,
    ) -> None:
        if text:
            f.write((MID, y or self.LINE_Y), text, "Bold", size, rgb or self.theme.text, fit=fit, spacing=spacing)

    def foot(self, f: Frame, text: str | None, rgb: Sequence[float]) -> None:
        """A word in a gauge's opening, between its two ends and inside the panel's edge."""
        if text:
            f.write((MID, self.FOOT_Y), text, "Bold", 30, rgb, spacing=2, fit=192)

    def gauge(
        self,
        f: Frame,
        value: float | None,
        scale: Scale,
        r_in: float = 168,
        r_out: float = 190,
        ticks: bool = True,
    ) -> RGB | None:
        """A 270-degree gauge of value on scale (just its track while value is missing), coloured along its length
        by what each value means. Returns the colour at its tip."""
        ring = self.kit.ring(r_in, r_out)
        f.paint(ring, ring.arc(1.0), self.theme.track, glow=0)
        if value is not None:
            f.paint(ring, ring.arc(scale.fill(value)), ring.gradient(self.theme, scale))
        if ticks:
            tick = self.kit.ring(r_in - 14, r_in - 8)
            f.paint(tick, tick.ticks(), self.theme.dim, glow=0)
        return self.colour(scale, value)


def limit(r: Snapshot, key: str) -> float:
    """A reading's limit: the config's or the hardware's, else a neutral default."""
    return r.max(key) or DEFAULT_MAX[key]


def pin_scale(r: Snapshot) -> tuple[float, float, Scale]:
    """A power connector's pin rating, the warning under it, and their scale."""
    rating = limit(r, "pins")
    warn = r.warn("pins") or 0.95 * rating
    return rating, warn, current(rating, warn)


def rnd(value: F64 | float | None, scale: float = 1) -> int | None:
    return None if value is None else round(float(value) * scale)


def joined(*parts: str | None) -> str:
    """Readings for one line, the missing ones left out."""
    return DOT.join(p for p in parts if p)


def fmt(value: float | None, form: str) -> str | None:
    return None if value is None else form.format(value)


def counts(values: F64 | None, scale: float) -> tuple[int, ...] | None:
    """An array's values rounded at a step of 1/scale, as a still key that ignores smaller changes."""
    return None if values is None else tuple(np.round(values * scale).astype(int).tolist())
