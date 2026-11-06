"""Designs for the CPU: its threads, temperature and load."""

from __future__ import annotations

import math
from collections.abc import Hashable

import numpy as np

from ..readings import Snapshot, Trail, TrailSpec
from .base import Design, counts, fmt, joined, limit, rnd
from .colour import LOAD, Theme, lerp, solid, temperature
from .frame import DASH, Pixels, Still, paint
from .geometry import MID
from .motion import Eased


class Crown(Design):
    name = "crown"
    shows = "CPU: temperature, every thread's load, total load, package power"
    about = (
        "The CPU's temperature inside a crown of radial bars, one per thread (the first at the top, clockwise), "
        "each as long as its thread is busy and in the colour of its load."
    )

    r: Snapshot  # the last update()'s readings

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.temp, self.load, self.threads = Eased(1), Eased(2), Eased(6, smooth=1.0)
        self.ring = self.kit.ring(164, 190)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.temp.step(r.number("cpu_c"), dt)
        self.load.step(r.number("cpu_load"), dt)
        self.threads.step(r.series("threads"), dt)
        self.r = r
        still = rnd(self.temp.value), rnd(self.load.value), rnd(r.number("cpu_w")), r.max("cpu_c")
        return (*still, counts(self.threads.value, 0.4)), None

    def still(self) -> Still:
        t, temp, ring = self.threads.value, self.temp.get(), self.ring
        f = self.frame(None if t is None else self.colour(LOAD, float(np.mean(t))))
        seg, cover = ring.bars(48 if t is None else len(t))  # missing: the empty tracks of a typical crown
        f.paint(ring, cover, self.theme.track, glow=0)
        if t is not None:
            load = np.clip(t / 100, 0, 1)
            reach = ring.r_in + 3 * self.kit.s + load[seg] * (ring.r_out - ring.r_in - 3 * self.kit.s)
            f.paint(ring, cover * np.clip(reach - ring.r + 0.5, 0, 1), solid(self.theme, LOAD.level(t))[seg])
        self.label(f, "CPU")
        f.number(246, temp, "°C", glow=self.colour(temperature(limit(self.r, "cpu_c")), temp))
        self.line(f, joined(fmt(self.load.get(), "{:.0f}%"), fmt(self.r.number("cpu_w"), "{:.0f} W")))
        return f.finish()


class Minimal(Design):
    name = "minimal"
    shows = "CPU temperature only"
    about = "One huge number in the colour of its heat against the CPU's limit, readable from across the room."

    r: Snapshot  # the last update()'s readings

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.temp = Eased(1)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.temp.step(r.number("cpu_c"), dt)
        self.r = r
        return (rnd(self.temp.value), r.max("cpu_c")), None

    def still(self) -> Still:
        t = self.temp.get()
        colour = self.colour(temperature(limit(self.r, "cpu_c")), t)
        f = self.frame(colour, 0.12)
        rgb = None if colour is None else lerp(self.theme.text, colour, 0.55)
        f.number(266, t, "°C", size=196, rgb=rgb, glow=colour, fit=176)
        f.write((MID, 318), "CPU", "Bold", 32, self.theme.dim, spacing=8)
        return f.finish()


class Orb(Design):
    name = "orb"
    shows = "CPU load (colour and speed) and temperature"
    about = (
        "A slow plasma orb in the colour of the CPU's load: it stirs faster as the CPU works. Its temperature "
        "rests in the middle."
    )
    fps = 15
    under_text = True

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.load, self.temp = Eased(3, tau=0.6), Eased(1)
        k = self.kit
        self.inside = np.flatnonzero(k.radius < 176 * k.s)
        self.x = k.dx.flat[self.inside] / (100 * k.s)
        self.y = k.dy.flat[self.inside] / (100 * k.s)
        rr = k.radius.flat[self.inside] / (176 * k.s)
        self.rim = np.clip((1 - rr) * 12, 0, 1)  # an antialiased edge
        self.shade = 0.55 + 0.45 * (1 - rr**2)
        self.phase = 0.0

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.load.step(r.number("cpu_load"), dt)
        self.temp.step(r.number("cpu_c"), dt)
        self.phase += dt * (0.25 + 1.2 * (self.load.get() or 0) / 100)
        return (rnd(self.temp.value), rnd(self.load.value)), self.animating(now)

    def still(self) -> Still:
        f = self.frame()
        f.number(232, self.temp.get(), "°C", size=96, fit=150)
        f.write((MID, 270), "CPU", "Bold", 26, self.theme.text, spacing=6)
        return f.finish()

    def moving(self, px: Pixels, now: float) -> None:
        p, x, y = self.phase, self.x, self.y
        v = (
            np.sin(x * 3.4 + p)
            + np.sin(y * 2.9 - p * 0.8)
            + np.sin((x + y) * 2.2 + p * 1.3)
            + np.sin(np.hypot(x + 0.5 * math.sin(p * 0.3), y) * 5.5 - p * 1.6)
        ) / 4  # -1..1
        load = self.load.get()
        # Its swirls in light, its colour from the load's level (kept within it): missing, a calm dim orb
        level = 0.05 if load is None else LOAD.level(load)
        colours = self.theme.heat(np.clip(level + 0.08 * v, 0, 1))
        light = (0.22 + 1.0 * ((v + 1) / 2) ** 1.4) * self.shade * self.rim * (0.45 if load is None else 1)
        flat = px.reshape(-1, 3)
        flat[self.inside] = flat[self.inside] * (1 - self.rim[:, None]) + colours * light[:, None]


class Radar(Design):
    name = "radar"
    shows = "CPU load now and over the last sweep (12 s)"
    about = (
        "A radar sweep that leaves the CPU load behind it as glowing spokes, fading as the sweep moves on; the "
        "load in the middle."
    )
    fps = 20
    SPOKES, TURN = 120, 12.0  # spokes round the ring, s per turn
    LOAD_TRAIL = TrailSpec("cpu_load", 0.1, TURN)
    trails = (LOAD_TRAIL,)

    trail: Trail  # set by update(), with now
    now: float

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.load = Eased(2)
        self.ring = self.kit.ring(118, 186)
        at = self.ring.angle / (360 / self.SPOKES)
        self.spoke = np.minimum(at.astype(int), self.SPOKES - 1)
        self.cover = self.ring.edge * np.clip(np.minimum(at % 1, 1 - at % 1) * 3 - 0.3, 0, 1)  # a gap between spokes

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.load.step(r.number("cpu_load"), dt)
        self.trail, self.now = r.trail(self.LOAD_TRAIL), now
        return (rnd(self.load.value),), self.animating(now)

    def still(self) -> Still:
        load = self.load.get()
        f = self.frame(self.colour(LOAD, load), 0.06)
        f.paint(self.ring, self.ring.edge * 0.25, self.theme.track, glow=0)
        f.number(238, load, "%", size=96, glow=self.colour(LOAD, load), fit=110)
        f.write((MID, 276), "CPU", "Bold", 26, self.theme.dim, spacing=6)
        return f.finish()

    def moving(self, px: Pixels, now: float) -> None:
        ring = self.ring
        sweep = (self.now / self.TURN * 360) % 360
        # Each spoke holds the load from when the sweep last passed it
        ages = ((sweep - (np.arange(self.SPOKES) + 0.5) * 360 / self.SPOKES) % 360) / 360
        t, v = np.array(self.trail.t), np.array(self.trail.v)
        values = np.interp(self.now - ages * self.TURN, t, v, left=np.nan) / 100
        spokes = values[self.spoke]
        known = ~np.isnan(spokes)
        spokes = np.nan_to_num(spokes)
        reach = ring.r_in + 4 * self.kit.s + spokes * (ring.r_out - ring.r_in - 4 * self.kit.s)
        fade = (1 - ages[self.spoke]) ** 1.5
        paint(
            px,
            ring,
            self.cover * np.clip(reach - ring.r + 0.5, 0, 1) * fade * known,
            solid(self.theme, LOAD.level(spokes * 100)),
        )
        off = (ring.angle - sweep + 180) % 360 - 180
        paint(px, ring, ring.edge * np.clip(1 - off**2 / 2.5, 0, 1) * 0.85, self.theme.text)


class Grid(Design):
    name = "grid"
    shows = "CPU: every thread's load as a dot, temperature and total load"
    about = (
        "The threads as a grid of dots that swell and change colour with their load, the CPU's temperature and "
        "load under them."
    )

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.threads, self.temp, self.load = Eased(6, smooth=1.0), Eased(1), Eased(2)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.threads.step(r.series("threads"), dt)
        self.temp.step(r.number("cpu_c"), dt)
        self.load.step(r.number("cpu_load"), dt)
        return (counts(self.threads.value, 0.3), rnd(self.temp.value), rnd(self.load.value)), None

    def still(self) -> Still:
        t = self.threads.value
        f = self.frame(None if t is None else self.colour(LOAD, float(np.mean(t))), 0.06)
        self.label(f, "CPU THREADS", y=88, spacing=5)
        n = 48 if t is None else len(t)  # missing: a typical grid's empty dots
        cols = math.ceil(math.sqrt(n * 4 / 3))  # about 4:3, in the 272 x 204 px box under the label
        rows = math.ceil(n / cols)
        pitch = min(272 / cols, 204 / rows)
        for i in range(n):
            row, col = divmod(i, cols)
            x, y = MID + (col - (cols - 1) / 2) * pitch, 213 - (rows - 1) / 2 * pitch + row * pitch
            f.disc(x, y, pitch * 0.35, self.theme.track, glow=0)
            if t is not None:
                load = min(max(float(t[i]), 0), 100)
                f.disc(x, y, pitch * (0.12 + 0.23 * load / 100), self.tone(LOAD, load), glow=0.8)
        text = joined(fmt(self.temp.get(), "{:.0f}°C"), fmt(self.load.get(), "{:.0f}%"))
        if text:
            f.write((MID, 336), text, "Black", 38, self.theme.text, fit=184)
        else:
            f.write((MID, 336), DASH, "Bold", 34, self.theme.dim)
        return f.finish()
