"""What sources report and designs read: readings, the limits that give them meaning, and their recent past."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Value = float | NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Reading:
    """One value as a source reports it. A series (each thread's load, each pin's current) is an array. max: the
    limit the hardware reports (a sensor's crit, a GPU's power limit or slowdown point); warn: a lower warning."""

    value: Value
    unit: str = ""
    max: float | None = None
    warn: float | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Meta:
    """What the config sets for a reading: limits the hardware doesn't report, or overrides them, and its label."""

    max: float | None = None
    warn: float | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class TrailSpec:
    """A reading kept every period s over span s, for the designs that draw its past."""

    key: str
    period: float
    span: float


class Trail:
    """One reading's recent past (t, v), NaN where it was missing. A sample within a period of the last is skipped."""

    def __init__(self, spec: TrailSpec) -> None:
        self.spec = spec
        self.size = round(spec.span / spec.period)
        self.t: list[float] = []
        self.v: list[float] = []

    def add(self, value: float | None, now: float) -> None:
        if not self.t or now - self.t[-1] >= self.spec.period * 0.999:
            self.t = [*self.t, now][-self.size :]
            self.v = [*self.v, np.nan if value is None else float(value)][-self.size :]


class Snapshot:
    """The fresh readings at one moment (a stale or missing one is absent), with the config's meta, the trails the
    designs asked for and the wall-clock time."""

    def __init__(
        self,
        readings: Mapping[str, Reading],
        wall: float,
        meta: Mapping[str, Meta] | None = None,
        trails: Mapping[TrailSpec, Trail] | None = None,
    ) -> None:
        self.readings, self.wall = readings, wall
        self.meta = meta or {}
        self.trails = trails or {}

    def number(self, key: str) -> float | None:
        reading = self.readings.get(key)
        return None if reading is None else float(reading.value)

    def series(self, key: str) -> NDArray[np.float64] | None:
        reading = self.readings.get(key)
        return None if reading is None else np.asarray(reading.value, np.float64)

    def count(self, key: str) -> int:
        """A count, 0 while it is missing (agent sessions working)."""
        return int(self.number(key) or 0)

    def flag(self, key: str) -> bool:
        return bool(self.number(key))

    def max(self, key: str) -> float | None:
        """The reading's limit: the config's, else the hardware's; None where neither sets one."""
        reading = self.readings.get(key)
        return self.meta.get(key, Meta()).max or (reading and reading.max) or None

    def warn(self, key: str) -> float | None:
        reading = self.readings.get(key)
        return self.meta.get(key, Meta()).warn or (reading and reading.warn) or None

    def label(self, key: str) -> str | None:
        reading = self.readings.get(key)
        return self.meta.get(key, Meta()).label or (reading and reading.label) or None

    def trail(self, spec: TrailSpec) -> Trail:
        try:
            return self.trails[spec]
        except KeyError:
            raise KeyError(f"trail {spec} not kept: a design that reads it lists it in its trails") from None
