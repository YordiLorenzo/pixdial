"""The CPU's, GPU's and PSU's temperatures, each against its own limit."""

from __future__ import annotations

from collections.abc import Hashable

from ..readings import Snapshot
from .base import Design, limit, rnd
from .colour import Theme, temperature
from .frame import DASH, Still
from .motion import Eased


class Thermals(Design):
    name = "thermals"
    shows = "CPU, GPU and PSU temperature, each against its own limit"
    reads = ("cpu_c", "gpu_c", "psu_c")
    needs = ("cpu_c",)
    about = (
        "Three temperatures as three rings, CPU outside, GPU, PSU inside, each on a scale from its own limit "
        "with a mark at that limit, and each value in the colour of what it means."
    )
    PARTS = (("CPU", "cpu_c", 174, 190), ("GPU", "gpu_c", 152, 166), ("PSU", "psu_c", 130, 144))

    limits: list[float]  # set by update()

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.temps = [Eased(1) for _ in self.PARTS]

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        for e, (_, key, *_) in zip(self.temps, self.PARTS, strict=True):
            e.step(r.number(key), dt)
        self.limits = [limit(r, key) for _, key, *_ in self.PARTS]
        return (*(rnd(e.value) for e in self.temps), *self.limits), None

    def still(self) -> Still:
        values = [e.get() for e in self.temps]
        scales = [temperature(top) for top in self.limits]
        levels = [float(scale.level(v)) for scale, v in zip(scales, values, strict=True) if v is not None]
        f = self.frame(self.theme.level(max(levels)) if levels else None, 0.07)
        for (_, _, r_in, r_out), scale, top, t in zip(self.PARTS, scales, self.limits, values, strict=True):
            self.gauge(f, t, scale, r_in, r_out, ticks=False)
            ring = self.kit.ring(r_in, r_out)
            f.paint(ring, ring.mark(scale.fill(top)), self.theme.text, glow=0)
        for i, ((name, *_), scale, t) in enumerate(zip(self.PARTS, scales, values, strict=True)):
            y = 152 + 50 * i
            f.write((116, y), name, "Bold", 26, self.theme.dim, anchor="lm")
            if t is None:
                f.write((284, y), DASH, "Bold", 30, self.theme.dim, anchor="rm")
            else:
                f.write((284, y), f"{t:.0f}°C", "Black", 44, self.tone(scale, t), anchor="rm")
        return f.finish()
