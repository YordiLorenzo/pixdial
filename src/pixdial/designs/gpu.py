"""Designs for the GPU: its power, temperature and power connector."""

from __future__ import annotations

from collections.abc import Hashable

import numpy as np

from ..readings import Snapshot
from .base import Design, counts, fmt, joined, limit, pin_scale, rnd
from .colour import Theme, share, temperature
from .frame import DASH, Frame, Still
from .geometry import MID
from .motion import Eased


class Gpu(Design):
    name = "gpu"
    shows = "GPU: board power of its power limit, temperature, use, the power connector's pins"
    about = (
        "The GPU's power on a 270° gauge of its power limit, temperature and use under it, and the power "
        "connector's pins (where a sensor reports them) as bars in the gauge's opening: equal bars are a healthy "
        "connector."
    )

    r: Snapshot  # the last update()'s readings

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.watts, self.pins = Eased(3), Eased(0.2, tau=0.4)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.watts.step(r.number("gpu_w"), dt)
        self.pins.step(r.series("pins"), dt)
        self.r = r
        still = rnd(self.watts.value), r.max("gpu_w"), r.number("gpu_c"), r.number("gpu_use")
        return (*still, counts(self.pins.value, 10)), None

    def still(self) -> Still:
        r, w = self.r, self.watts.get()
        scale = share(limit(r, "gpu_w"))
        f = self.frame(self.colour(scale, w), 0.10)
        colour = self.gauge(f, w, scale)
        self.label(f, "GPU")
        f.number(246, w, "W", glow=colour)
        self.line(f, joined(fmt(r.number("gpu_c"), "{:.0f}°C"), fmt(r.number("gpu_use"), "{:.0f}%")))
        self.connector(f, 330, 40)
        return f.finish()

    def connector(self, f: Frame, top: float, height: float, width: float = 12, pitch: float = 20) -> None:
        """The connector's pins as small bars, where a sensor reports them."""
        p = self.pins.value
        if p is None:
            return
        rating, _, scale = pin_scale(self.r)
        x0 = MID - ((len(p) - 1) * pitch + width) / 2
        for i, amps in enumerate(p):
            x = x0 + i * pitch
            f.rect(x, top, width, height, self.theme.track, glow=0)
            h = round(height * min(amps / rating, 1))
            if h:
                f.rect(x, top + height - h, width, h, self.tone(scale, amps))


class Twin(Design):
    name = "twin"
    shows = "GPU temperature (outer ring, against its slowdown point) and power (inner, of its limit)"
    about = (
        "Two rings for the GPU: temperature outside, power inside, the watts big and the temperature in its own "
        "colour under them."
    )

    r: Snapshot  # the last update()'s readings

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.temp, self.watts = Eased(1), Eased(3)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.temp.step(r.number("gpu_c"), dt)
        self.watts.step(r.number("gpu_w"), dt)
        self.r = r
        return (rnd(self.temp.value), rnd(self.watts.value), r.max("gpu_w"), r.max("gpu_c")), None

    def still(self) -> Still:
        t, w = self.temp.get(), self.watts.get()
        power, heat = share(limit(self.r, "gpu_w")), temperature(limit(self.r, "gpu_c"))
        # Lit in the colour of whichever is further along (red over the green of the other)
        lit = [self.tone(scale, v) for scale, v in ((heat, t), (power, w)) if v is not None]
        f = self.frame(max(lit, key=lambda c: c[0] - c[1], default=None), 0.08)
        self.gauge(f, t, heat, 174, 190, ticks=False)
        self.gauge(f, w, power, 150, 164, ticks=False)
        self.label(f, "GPU", y=110)
        f.number(234, w, "W", size=112, glow=self.colour(power, w), fit=136)
        if t is None:
            f.write((MID, 284), DASH, "Bold", 34, self.theme.dim)
        else:
            f.write((MID, 284), f"{t:.0f}°C", "Black", 46, self.tone(heat, t), fit=136)
        return f.finish()


class Pins(Design):
    name = "pins"
    shows = "GPU power connector: each pin's current, the total current and power, balance"
    about = (
        "The GPU's power connector pin by pin, where a sensor reports them: a tall bar per pin with its amps, a "
        "line at the warning, and the connector's total and balance (smallest over largest) under them."
    )

    r: Snapshot  # the last update()'s readings

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.pins = Eased(0.05, tau=0.4)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.pins.step(r.series("pins"), dt)
        self.r = r
        still = rnd(r.number("gpu_w")), rnd(r.number("pin_total"), 10), rnd(r.number("pin_balance"), 100)
        return (counts(self.pins.value, 20), *still), None

    def still(self) -> Still:
        p, r = self.pins.value, self.r
        rating, warn, scale = pin_scale(r)
        f = self.frame(None if p is None else self.tone(scale, float(np.max(p))), 0.10)
        self.label(f, r.label("pins") or "PINS", y=72, spacing=3)
        n = 6 if p is None else len(p)  # missing: a typical connector's empty bars
        top, height = 134, 148
        pitch = min(40.0, 236 / n)
        width = round(pitch * 0.65)
        x0 = MID - ((n - 1) * pitch + width) / 2
        warn_y = top + height * (1 - warn / rating)
        for i in range(n):
            x = x0 + i * pitch
            f.rect(x, top, width, height, self.theme.track, glow=0)
            if p is not None:
                amps = float(p[i])
                colour = self.tone(scale, amps)
                h = round(height * min(amps / rating, 1))
                if h:
                    f.rect(x, top + height - h, width, h, colour)
                text_rgb = colour if amps >= warn else self.theme.text
                f.write((x + width / 2, top - 16), f"{amps:.1f}", "Bold", 22, text_rgb)
            f.write((x + width / 2, top + height + 15), str(i + 1), "Bold", 20, self.theme.dim)
        f.rect(x0 - 8, warn_y - 1, (n - 1) * pitch + width + 16, 2, self.theme.levels[2], glow=0.3)
        if p is None:
            f.write((MID, 330), "NO DATA", "Bold", 26, self.theme.dim, spacing=3)
            return f.finish()
        # The total and balance come from the sensor's own frames: the bars are each pin's maximum over a window, and
        # a pin that dropped for a moment would not show in their ratio
        total = joined(fmt(r.number("pin_total"), "{:.1f} A"), fmt(r.number("gpu_w"), "{:.0f} W"))
        self.line(f, total, y=330, size=34, fit=190)
        balance = r.number("pin_balance")
        if balance is not None:
            f.write((MID, 364), f"BALANCE {balance:.2f}", "Bold", 22, self.theme.dim, spacing=2, fit=190)
        return f.finish()
