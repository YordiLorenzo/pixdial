"""Shown values that glide to their readings, so arcs sweep and numbers count instead of jumping."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

F64 = NDArray[np.float64]


class Eased:
    """A shown value (or array) that glides to its reading in about 0.6 s. A reading less than `still` from the one it
    follows is left out: an idle machine's jitter of a watt or a degree would otherwise keep every screen redrawing.
    smooth: a time constant (s) the readings are averaged over first, for readings that jitter more than `still` from
    one sample to the next (a thread's load every 0.5 s). A reading of another shape (a CPU gone offline) starts it
    over."""

    def __init__(self, still: float, tau: float = 0.18, smooth: float = 0.0) -> None:
        self.still, self.tau, self.smooth = still, tau, smooth
        self.value: F64 | None = None
        self.target: F64 | None = None
        self.mean: F64 | None = None

    def step(self, reading: ArrayLike | None, dt: float) -> F64 | None:
        x = None if reading is None else np.asarray(reading, np.float64)
        if x is None or self.value is None or self.target is None or self.mean is None or x.shape != self.value.shape:
            self.value = self.target = self.mean = x
            return x
        if self.smooth:
            self.mean = x = x + (self.mean - x) * math.exp(-dt / self.smooth)
        self.target = np.where(np.abs(x - self.target) >= self.still, x, self.target)
        self.value = self.target + (self.value - self.target) * math.exp(-dt / self.tau)
        return self.value

    def get(self) -> float | None:
        return None if self.value is None else float(self.value)
