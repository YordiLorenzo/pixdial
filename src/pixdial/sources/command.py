"""Readings from any program: it runs every period seconds and prints them."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from typing import Any

import numpy as np

from ..readings import Reading, Value
from .base import Source


class Command(Source):
    """run: the program and its arguments (no shell). It prints either one number, the reading `key`, or a JSON
    object of readings: {"key": 42, "series": [1, 2], "other": {"value": 61, "unit": "°C", "max": 95}}."""

    def __init__(self, run: Sequence[str], key: str | None = None, period: float = 5.0) -> None:
        if not run:
            raise ValueError("run: the program to run, as a list")
        self.run, self.key, self.period = list(run), key, period

    def read(self) -> dict[str, Reading]:
        try:
            done = subprocess.run(self.run, capture_output=True, text=True, timeout=self.period, check=True)
        except subprocess.SubprocessError as error:  # it failed or took too long
            raise OSError(str(error)) from error
        if self.key is not None:
            return {self.key: Reading(number(done.stdout.strip()))}
        return {key: reading(value) for key, value in json.loads(done.stdout).items()}


def reading(value: Any) -> Reading:
    if not isinstance(value, dict):
        return Reading(number(value))
    top, warn = (None if value.get(k) is None else float(number(value[k])) for k in ("max", "warn"))
    unit, label = value.get("unit", ""), value.get("label")
    if not isinstance(unit, str) or not isinstance(label, str | None):
        raise ValueError(f"unit and label must be text: {value!r}")
    return Reading(number(value["value"]), unit, top, warn, label)


def number(value: Any) -> Value:
    """A number or a flat, non-empty list of numbers; NaN and infinity are refused (a design can't place them)."""
    out = np.asarray(value, np.float64) if isinstance(value, list) else float(value)
    if np.ndim(out) > 1 or np.size(out) == 0 or not np.all(np.isfinite(out)):
        raise ValueError(f"not a number or a flat list of numbers: {value!r}")
    return out
