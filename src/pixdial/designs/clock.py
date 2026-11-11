"""A clock with the system's load round it."""

from __future__ import annotations

import datetime
from collections.abc import Hashable

from ..readings import Snapshot
from .base import Design, limit, rnd
from .colour import LOAD, Theme, lerp
from .frame import Pixels, Still, disc, glow_disc, paint
from .geometry import MID, on_circle
from .motion import Eased


class Clock(Design):
    name = "clock"
    shows = "The time and date, the system load (the higher of CPU and GPU), a seconds comet"
    reads = ("cpu_load", "gpu_w")
    about = (
        "A calm clock: hours and minutes, the date, a thin ring in the load colour and a comet that runs the "
        "seconds round."
    )
    fps = 10

    wall: float  # set by update()

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.load = Eased(3)
        self.ring = self.kit.ring(184, 191)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        cpu, gpu = r.number("cpu_load"), r.number("gpu_w")
        gpu = None if gpu is None else gpu / limit(r, "gpu_w") * 100
        self.load.step(max((x for x in (cpu, gpu) if x is not None), default=None), dt)
        self.wall = r.wall
        return (int(self.wall // 60), rnd(self.load.value)), self.animating(now)

    def still(self) -> Still:
        load = self.load.get()
        colour = self.colour(LOAD, load) or self.theme.dim
        f = self.frame(None if load is None else colour, 0.05)
        f.paint(self.ring, self.ring.edge, lerp(self.theme.track, colour, 0.35), glow=0.4)
        t = datetime.datetime.fromtimestamp(self.wall)
        f.write((MID, 205), t.strftime("%H:%M"), "Black", 118, self.theme.text, fit=176)
        f.write((MID, 290), t.strftime("%a %d %b").upper(), "Bold", 28, self.theme.dim, spacing=4, fit=176)
        return f.finish()

    def moving(self, px: Pixels, now: float) -> None:
        sec = self.wall % 60
        colour = self.colour(LOAD, self.load.get()) or self.theme.dim
        paint(px, self.ring, self.ring.edge * self.ring.trail(sec * 6, 40), colour)
        x, y = on_circle(187.5, sec * 6)
        glow_disc(px, self.kit, x, y, 10, colour, 0.5)
        disc(px, self.kit, x, y, 5, self.theme.text)
