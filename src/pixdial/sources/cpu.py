"""The CPU's load from /proc/stat and its package power from the RAPL energy counter."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from ..readings import Reading
from .base import Source


class Cpu(Source):
    """cpu_load: the whole CPU's busy share, threads: each thread's (both in %, over the last period)."""

    period = 0.5

    def __init__(self, stat: str = "/proc/stat") -> None:
        self.stat = Path(stat)
        self.last: tuple[NDArray[np.float64], NDArray[np.float64]] | None = None

    def read(self) -> dict[str, Reading]:
        rows = [line.split() for line in self.stat.read_text().splitlines() if line.startswith("cpu")]
        times = np.array([[int(x) for x in row[1:9]] for row in rows], dtype=np.float64)
        idle, total = times[:, 3] + times[:, 4], times.sum(axis=1)
        last, self.last = self.last, (idle, total)
        if last is None or len(last[0]) != len(idle):  # the first sample, or a CPU came online
            return {}
        busy = 100 - 100 * (idle - last[0]) / np.maximum(total - last[1], 1)
        return {"cpu_load": Reading(float(busy[0]), "%"), "threads": Reading(busy[1:], "%")}


class Rapl(Source):
    """cpu_w: the CPU package's power from its energy counter (reading it needs its file readable by the user)."""

    def __init__(self, path: str = "/sys/class/powercap/intel-rapl:0/energy_uj") -> None:
        self.path = Path(path)
        self.last: tuple[int, float] | None = None

    def read(self) -> dict[str, Reading]:
        energy, now = int(self.path.read_text()), time.monotonic()
        last, self.last = self.last, (energy, now)
        if last is None or energy < last[0]:  # the first sample, or the counter wrapped
            return {}
        return {"cpu_w": Reading((energy - last[0]) / 1e6 / (now - last[1]), "W")}
