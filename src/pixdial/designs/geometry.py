"""The round panel's pixel grids and rings at one scale. Designs give every size in the panel's 400 px."""

from __future__ import annotations

import functools
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import ImageFont

from .colour import Scale, Theme

SIZE = 400  # px across the panel
MID = (SIZE - 1) / 2
START, SWEEP = 225.0, 270.0  # gauges: from 7:30 clockwise over the top to 4:30, open at the bottom
FONTS = Path(__file__).parent.parent / "fonts"  # Lato: its figures are tabular, so a number keeps its width

F32 = NDArray[np.float32]


class Kit:
    """The pixel grids, rings and fonts for one scale (1 for a panel, 2 for sharp previews)."""

    def __init__(self, scale: int) -> None:
        self.s, self.size = scale, SIZE * scale
        self.mid = (self.size - 1) / 2
        y, x = np.mgrid[0 : self.size, 0 : self.size].astype(np.float32)
        self.dx, self.dy = x - self.mid, y - self.mid
        self.radius = np.hypot(self.dx, self.dy)  # px
        self.angle = np.degrees(np.arctan2(self.dx, -self.dy)) % 360  # clockwise from 12 o'clock
        self.ambient = np.exp(-((self.radius / (165 * scale)) ** 2))[..., None]

    @functools.cache
    def ring(self, r_in: float, r_out: float) -> Ring:
        return Ring(self, r_in, r_out)

    @functools.cache
    def font(self, weight: str, size: float) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(FONTS / f"Lato-{weight}.ttf"), round(size * self.s))

    @functools.cache
    def advance(self, weight: str, size: float, letter: str) -> float:
        """A letter's advance in px at this scale (measuring one takes about 0.1 ms, and spaced text measures each)."""
        return self.font(weight, size).getlength(letter)

    @functools.cache
    def background(self, theme: Theme) -> F32:
        edge = np.clip(self.radius / (200 * self.s), 0, 1)[..., None]
        inner, outer = (np.array(c, np.float32) for c in theme.bg)
        return inner * (1 - edge) + outer * edge


@functools.cache
def kit(scale: int) -> Kit:
    return Kit(scale)


class Ring:
    """The pixels of an annulus with their radius and angle, so an arc on it is a few array operations."""

    def __init__(self, kit: Kit, r_in: float, r_out: float) -> None:
        s = self.s = kit.s
        self.r_in, self.r_out = r_in * s, r_out * s
        self.mid, self.half = (self.r_in + self.r_out) / 2, (self.r_out - self.r_in) / 2
        self.idx = np.flatnonzero((kit.radius > self.r_in - 1) & (kit.radius < self.r_out + 1))
        self.r, self.angle = kit.radius.flat[self.idx], kit.angle.flat[self.idx]
        self.x, self.y = kit.dx.flat[self.idx], kit.dy.flat[self.idx]
        self.edge = np.clip(self.r - self.r_in + 0.5, 0, 1) * np.clip(self.r_out - self.r + 0.5, 0, 1)
        # Degrees along the gauge from START, -45 to 315: the start cap's pixels lie just before 0, not near 360
        self.pos = (self.angle - START + 45) % 360 - 45

    @functools.cache
    def gradient(self, theme: Theme, scale: Scale) -> F32:
        """The theme's level colours along the gauge for a scale: each pixel coloured as the value at its place."""
        return theme.heat(scale.level(scale.lo + self.pos / SWEEP * (scale.hi - scale.lo)))

    @functools.cache
    def ticks(self, n: int = 11) -> F32:
        """Coverage of n antialiased ticks spread over the gauge, about 2.5 px wide."""
        step = SWEEP / (n - 1)
        off = np.abs(self.pos - step * np.clip(np.round(self.pos / step), 0, n - 1))
        return self.edge * np.clip(1.25 * self.s - np.radians(off) * self.r + 0.5, 0, 1)

    @functools.cache
    def bars(self, n: int) -> tuple[NDArray[np.intp], F32]:
        """n radial bars round the ring: each pixel's bar, and their coverage with a 2 px gap between them."""
        at = self.angle / (360 / n)
        gap = np.minimum(at % 1, 1 - at % 1) * math.radians(360 / n) * self.r  # px from its bar's side
        return np.minimum(at.astype(int), n - 1), self.edge * np.clip(gap - 1.0 * self.s, 0, 1)

    def mark(self, f: float) -> F32:
        """Coverage of a thin line across the ring at f (0-1) along the gauge: a limit."""
        off = np.abs(self.pos - SWEEP * f)
        return self.edge * np.clip(1.0 * self.s - np.radians(off) * self.r + 0.5, 0, 1)

    def cap(self, angle: float) -> F32:
        a = math.radians(angle)
        d = np.hypot(self.x - self.mid * math.sin(a), self.y + self.mid * math.cos(a))
        return np.clip(self.half - d + 0.5, 0, 1)

    def arc(self, f: float) -> F32:
        """Coverage of the gauge's arc filled to f (0-1), with round ends."""
        end = SWEEP * min(max(f, 0.0), 1.0)
        body = self.edge * ((self.pos >= 0) & (self.pos <= end))
        return np.maximum(body, np.maximum(self.cap(START), self.cap(START + end)))

    def trail(self, head: float, length: float) -> F32:
        """How much of a comet each pixel's angle holds: 1 at the head (degrees), fading over length degrees behind."""
        return np.clip(1 - (head - self.angle) % 360 / length, 0, 1) ** 1.6

    def segment(self, start: float, sweep: float) -> F32:
        """Coverage of a flat-ended piece of the ring from start over sweep degrees."""
        return self.edge * ((self.angle - start) % 360 <= sweep)


def on_circle(r: float, angle: float) -> tuple[float, float]:
    a = math.radians(angle)
    return MID + r * math.sin(a), MID - r * math.cos(a)


def inside(box: tuple[float, float, float, float], radius: float) -> bool:
    """Whether a box (x0, y0, x1, y1, in 400 px) lies within the circle of radius around the middle."""
    x0, y0, x1, y1 = box
    return bool(max(abs(x0 - MID), abs(x1 - MID)) ** 2 + max(abs(y0 - MID), abs(y1 - MID)) ** 2 <= radius**2)
