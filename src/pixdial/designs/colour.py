"""Themes, and the scales that say what a value means: where on a ring it sits and which colour it takes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

RGB = tuple[float, float, float]
NEEDS_YOU: RGB = (255, 0, 200)  # an agent waiting for its user
QUOTA_RGB: RGB = (217, 119, 87)  # an agent pool's quota
THRESHOLDS = (0.15, 0.5, 0.85)  # where a level fraction turns load, heavy and extreme


class Theme:
    """Four levels (idle, load, heavy, extreme: a Scale places them for each reading), the text colours, the dark
    track, the background's middle and edge, and three part colours (a split ring's first, second and rest)."""

    def __init__(
        self,
        levels: Sequence[RGB],
        text: RGB,
        dim: RGB,
        track: RGB,
        bg: tuple[RGB, RGB],
        parts: tuple[RGB, RGB, RGB],
    ) -> None:
        self.levels, self.text, self.dim, self.track, self.bg, self.parts = levels, text, dim, track, bg, parts
        a, b, c, d = levels
        stops = [(0, a), (0.135, a), (0.165, b), (0.485, b), (0.515, c), (0.835, c), (0.865, d), (1, d)]
        self.xs = [x for x, _ in stops]
        self.cs = np.array([rgb for _, rgb in stops], np.float32)

    def heat(self, f: ArrayLike) -> NDArray[np.float32]:
        """Colours for level fractions f (0-1), shape (len(f), 3); short blends at the thresholds."""
        f = np.clip(np.asarray(f, np.float32), 0, 1)
        return np.stack([np.interp(f, self.xs, self.cs[:, i]) for i in range(3)], axis=-1)

    def level(self, f: float) -> RGB:
        r, g, b = (float(c) for c in self.heat([f])[0])
        return r, g, b


THEMES = {
    # warm white (about 3000 K), green, orange, red
    "warm": Theme(
        [(255, 158, 78), (52, 232, 98), (255, 106, 20), (255, 40, 40)],
        (255, 236, 214), (140, 126, 112), (38, 35, 40), ((15, 14, 17), (3, 3, 4)),
        ((255, 158, 78), (60, 220, 200), (128, 116, 108)),
    ),
    "ember": Theme(
        [(150, 82, 34), (255, 150, 50), (255, 92, 14), (255, 36, 24)],
        (255, 218, 178), (140, 108, 84), (40, 30, 26), ((17, 12, 10), (4, 3, 2)),
        ((255, 150, 50), (255, 214, 160), (128, 100, 84)),
    ),
    "ice": Theme(
        [(150, 200, 255), (60, 230, 205), (185, 120, 255), (255, 60, 115)],
        (226, 240, 255), (112, 126, 148), (30, 34, 44), ((12, 14, 19), (2, 3, 5)),
        ((150, 200, 255), (60, 230, 205), (104, 114, 134)),
    ),
}  # fmt: skip


@dataclass(frozen=True)
class Scale:
    """A reading's range on a ring (lo to hi) and the values where it turns load, heavy and extreme: those map to
    the theme's level thresholds, so its colour says what the value means."""

    lo: float
    hi: float
    load: float
    heavy: float
    extreme: float

    def fill(self, v: float) -> float:
        return min(max((v - self.lo) / (self.hi - self.lo), 0.0), 1.0)

    def level(self, v: float | NDArray[Any]) -> NDArray[np.float64] | np.float64:
        return np.interp(v, (self.lo, self.load, self.heavy, self.extreme, self.hi), (0, *THRESHOLDS, 1))


def share(top: float) -> Scale:
    """A share of a maximum (a power limit, a PSU's rating, 100 %): load from 15 %, heavy 50, extreme 85, full at
    the maximum."""
    return Scale(0, top, 0.15 * top, 0.5 * top, 0.85 * top)


def temperature(top: float) -> Scale:
    """A temperature against its limit (a sensor's crit or slowdown point): load from 40 % of the way from 20 °C to
    the limit, heavy from 75 %, extreme at the limit; the ring runs 10 °C past it, so a value at the limit isn't
    pinned."""
    return Scale(20, top + 10, 20 + 0.4 * (top - 20), 20 + 0.75 * (top - 20), top)


def current(rating: float, warn: float) -> Scale:
    """A current against its rating and the warning under it: load from a tenth of the rating."""
    return Scale(0, rating, 0.1 * rating, warn, rating)


LOAD = share(100)


def solid(theme: Theme, level: ArrayLike) -> NDArray[np.float32]:
    """The colours of single values' levels: each its band's own colour, never a blend between two (a reading just
    under a threshold would read olive); gradients along a ring keep their short blends."""
    return np.asarray(theme.levels, np.float32)[np.searchsorted(THRESHOLDS, level, side="right")]


def lerp(a: Sequence[float], b: Sequence[float], t: float) -> RGB:
    r, g, b_ = (x + (y - x) * t for x, y in zip(a, b, strict=True))
    return r, g, b_
