"""Made-up readings of a busy workstation, for rendering designs without hardware (previews, the gallery, tests).

States: idle; busy (a build and a GPU job, the CPU near its limit, three agent sessions working); waiting (an agent
session waiting for you); full (everything at its limit); missing (no readings at all). The machine reports the limits
a real one would (an NVML power limit and slowdown point, a PSU's temperature crit).
"""

from __future__ import annotations

import datetime
import math

import numpy as np

from .readings import Reading

STATES = ("idle", "busy", "waiting", "full", "missing")
START = datetime.datetime(2026, 11, 4, 21, 42).timestamp()  # the clock shows 21:42


def readings(state: str, t: float) -> dict[str, Reading]:
    """The readings at second t of a state."""
    if state == "missing":
        return {}
    rng = np.random.default_rng(int(t * 10) + STATES.index(state))
    wave = math.sin(t / 9)
    if state == "idle":
        threads = np.clip(rng.gamma(1.2, 1.5, 48), 0, 100)
        cpu_w, cpu_c = 41 + 2 * wave, 34 + wave
        gpu_w, gpu_c, use = 10.5 + wave, 31, 0
        pins = [0.38, 0.41, 0.36, 0.40, 0.37, 0.39]
        psu_c, fan, quota, working, waiting = 33, 0, 89.8, 0, False
    elif state == "busy":
        threads = np.clip(rng.normal(55 + 25 * math.sin(t / 7), 22, 48), 0, 100)
        cpu_w, cpu_c = 230 + 60 * wave, 93 + 2 * wave
        gpu_w, gpu_c, use = 455 + 40 * math.sin(t / 5), 71, 98
        pins = [7.4, 7.1, 7.6, 7.3, 6.9, 7.5]
        psu_c, fan, quota, working, waiting = 46, 640, 58, 3, False
    elif state == "waiting":
        threads = np.clip(rng.normal(16, 9, 48), 0, 100)
        cpu_w, cpu_c = 92 + 8 * wave, 57 + wave
        gpu_w, gpu_c, use = 120 + 10 * wave, 47, 31
        pins = [1.8, 1.7, 1.9, 1.8, 1.6, 1.8]
        psu_c, fan, quota, working, waiting = 39, 0, 31, 1, True
    else:  # full
        threads = np.full(48, 100.0)
        cpu_w, cpu_c = 352 + 3 * wave, 95
        gpu_w, gpu_c, use = 600, 93, 100
        pins = [9.0, 8.7, 9.3, 9.1, 8.6, 9.0]
        psu_c, fan, quota, working, waiting = 52, 980, 12.4, 3, True
    psu_w = 60 + cpu_w * 1.08 + gpu_w * 1.04 + (240 * max(0, math.sin(t / 15)) if state == "busy" else 0)
    return {
        "cpu_load": Reading(float(np.mean(threads)), "%"),
        "threads": Reading(threads, "%"),
        "cpu_c": Reading(cpu_c, "°C"),
        "cpu_w": Reading(cpu_w, "W"),
        "gpu_w": Reading(gpu_w, "W", max=600),
        "gpu_c": Reading(gpu_c, "°C", max=93),
        "gpu_use": Reading(use, "%"),
        "pins": Reading(np.array(pins), "A"),
        "pin_total": Reading(sum(pins) * 0.98, "A"),
        "pin_balance": Reading(min(pins) / max(pins) * 0.97),
        "psu_w": Reading(psu_w, "W"),
        "psu_c": Reading(psu_c, "°C", max=70),
        "psu_fan": Reading(fan, "rpm"),
        "quota": Reading(quota, "%"),
        "working": Reading(working),
        "waiting": Reading(waiting),
    }
