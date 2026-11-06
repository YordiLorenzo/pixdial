"""Designs for the power supply: its output, where the watts go, and its recent past."""

from __future__ import annotations

import colorsys
from collections.abc import Hashable

import numpy as np

from ..readings import Snapshot, Trail, TrailSpec
from .agents import agents, pulse, sessions
from .base import Design, counts, fmt, joined, limit, rnd
from .colour import NEEDS_YOU, QUOTA_RGB, Theme, lerp, share
from .frame import Pixels, Still, add, paint
from .geometry import F32, MID
from .motion import Eased


class Psu(Design):
    name = "psu"
    shows = "PSU DC output of its rating, PSU temperature and fan, an agent pool's quota and sessions"
    about = (
        "The PSU's output on a gauge of its rating, and the agents as an inner ring: their quota in coral, a "
        "rainbow comet while they work, magenta pulses while one waits for you."
    )
    fps = 30
    previews = ("busy", "idle", "waiting")
    COMET = 70  # degrees of tail

    r: Snapshot  # the last update()'s readings
    working: int  # set by update(), with waiting
    waiting: bool

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.watts, self.quota = Eased(5), Eased(0.5, tau=0.4)
        self.ring = self.kit.ring(153, 160)
        self.halo = self.kit.ring(145, 168)
        self.rainbow = hues(self.ring.angle)
        self.halo_rgb = hues(self.halo.angle)
        self.falloff = np.exp(-(((self.halo.r - self.ring.mid) / (8 * self.kit.s)) ** 2))
        self.comet = self.pulse = 0.0

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.watts.step(r.number("psu_w"), dt)
        self.quota.step(r.number("quota"), dt)
        self.r = r
        self.working, self.waiting = working, waiting = agents(r)
        # degrees/s: a turn in 10 s for one busy session, faster for more
        self.comet = (self.comet + dt * (36 + 18 * min(working - 1, 2))) % 360 if working else 0.0
        self.pulse = pulse(now) if waiting else 0.0
        still = (
            rnd(self.watts.value),
            r.max("psu_w"),
            r.number("psu_c"),
            r.number("psu_fan"),
            rnd(self.quota.value, 4),
            working,
            waiting,
            round(self.pulse * 10),
        )
        return still, self.animating(now) if working and not waiting else None

    def still(self) -> Still:
        r, w, waiting = self.r, self.watts.get(), self.waiting
        scale = share(limit(r, "psu_w"))
        f = self.frame(NEEDS_YOU if waiting else self.colour(scale, w), 0.10)
        colour = self.gauge(f, w, scale, ticks=False)
        self.label(f, "PSU")
        f.number(246, w, "W", glow=colour, fit=146)
        fan = r.number("psu_fan")
        fan_text = "fan off" if fan == 0 else fmt(fan, "{:.0f} rpm")
        self.line(f, joined(fmt(r.number("psu_c"), "{:.0f}°C"), fan_text), fit=146)
        ring, quota = self.ring, self.quota.get()
        if waiting:
            f.paint(ring, ring.arc(1.0), lerp(self.theme.track, NEEDS_YOU, 0.25 + 0.75 * self.pulse))
            self.foot(f, "NEEDS YOU", lerp(self.theme.dim, NEEDS_YOU, 0.4 + 0.6 * self.pulse))
            return f.finish()
        f.paint(ring, ring.arc(1.0), self.theme.track, glow=0)
        if quota is not None:
            f.paint(ring, ring.arc(quota / 100), QUOTA_RGB, glow=0.3)
        if self.working:
            self.foot(f, sessions(self.working), self.theme.text)
        else:
            self.foot(f, fmt(quota, "QUOTA {:.0f}%"), self.theme.dim)
        return f.finish()

    def moving(self, px: Pixels, now: float) -> None:
        if not self.working or self.waiting:
            return
        head = self.comet
        a = self.halo.trail(head, self.COMET) * self.falloff * 0.45  # its glow, without a blur
        on = a > 0.01
        add(px.reshape(-1, 3), self.halo.idx[on], self.halo_rgb[on] * a[on, None])
        paint(px, self.ring, self.ring.edge * self.ring.trail(head, self.COMET), self.rainbow)


def hues(angles: F32) -> F32:
    """A rainbow round the panel: each pixel's hue from its angle."""
    return np.array([colorsys.hsv_to_rgb(a / 360, 0.85, 1) for a in angles], np.float32) * 255


class Flow(Design):
    name = "flow"
    shows = "PSU output split into CPU package, GPU board and the rest (board, RAM, drives, fans)"
    about = (
        "Where the watts go: a ring split by the CPU's and the GPU's own power figures, the rest of the PSU's "
        "output after them, with the total in the middle."
    )
    NAMES = ("CPU", "GPU", "REST")

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.parts = Eased(4)
        self.ring = self.kit.ring(152, 186)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        psu, cpu, gpu = r.number("psu_w"), r.number("cpu_w"), r.number("gpu_w")
        parts = None if psu is None or cpu is None or gpu is None else [cpu, gpu, max(psu - cpu - gpu, 0)]
        self.parts.step(parts, dt)
        return (counts(self.parts.value, 1),), None

    def still(self) -> Still:
        ring, v, colours = self.ring, self.parts.value, self.theme.parts
        f = self.frame(None if v is None else colours[1], 0.06)
        f.paint(ring, ring.edge, self.theme.track, glow=0)
        self.label(f, "POWER", y=110)
        if v is None:
            f.number(222, None, "W", size=100)
            return f.finish()
        total, start = float(np.sum(v)), 0.0
        for rgb, watts in zip(colours, v, strict=True):
            sweep = 360 * float(watts) / max(total, 1)
            if sweep > 4:  # a 2-degree gap each side
                f.paint(ring, ring.segment(start + 2, sweep - 4), rgb, glow=0.8)
            start += sweep
        f.number(222, total, "W", size=100, glow=colours[1], fit=140)
        for i, (name, rgb, watts) in enumerate(zip(self.NAMES, colours, v, strict=True)):  # names right, watts left
            y = 254 + 26 * i
            f.write((MID - 8, y), name, "Bold", 22, rgb, anchor="rm")
            f.write((MID + 8, y), f"{float(watts):.0f} W", "Bold", 22, rgb, anchor="lm")
        return f.finish()


class History(Design):
    name = "history"
    shows = "PSU DC output now and over the last two minutes, on the PSU's rating"
    about = (
        "The PSU's output as a big number over a filled graph of the last two minutes on a fixed scale (zero to "
        "the PSU's rating, lines at a third and two thirds), in the load colours: a long job reads as a shape."
    )
    X0, X1, Y0, Y1 = 72, 328, 218, 326  # the graph
    WATTS = TrailSpec("psu_w", 1.0, 120.0)
    trails = (WATTS,)

    trail: Trail  # set by update(), with top
    top: float

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.watts = Eased(5)

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.watts.step(r.number("psu_w"), dt)
        self.trail, self.top = r.trail(self.WATTS), limit(r, "psu_w")
        return (rnd(self.watts.value), self.top, self.trail.t[-1]), None  # each sample moves the graph

    def still(self) -> Still:
        w, top = self.watts.get(), self.top
        scale = share(top)
        f = self.frame(self.colour(scale, w), 0.08)
        self.label(f, "PSU  2 MIN", y=88)
        f.number(196, w, "W", size=104, glow=self.colour(scale, w), fit=170)
        k, s = self.kit, self.kit.s
        x0, x1, y0, y1 = self.X0, self.X1, self.Y0, self.Y1
        for third in (1, 2):  # the scale is fixed, so a shape means the same every time
            f.rect(x0, y1 - (y1 - y0) * third / 3, x1 - x0, 1, self.theme.track, glow=0)
        f.rect(x0, y1, x1 - x0, 2, self.theme.track, glow=0)
        trail = self.trail
        values = np.array(trail.v)
        if np.count_nonzero(~np.isnan(values)) < 2:  # a graph needs two points
            return f.finish()
        xs = np.linspace(x0, x1, trail.size)[-len(values) :]
        cols = np.arange(round(xs[0] * s), round(x1 * s))  # from the oldest sample: a fresh start fills from the right
        at = np.interp(cols / s, xs, values)  # NaN where a reading was missing: no fill there
        height = y1 - (y1 - y0) * np.clip(at, 0, top) / top
        colours = self.theme.heat(scale.level(np.nan_to_num(at)))
        yy = np.arange(k.size)[:, None]
        known = ~np.isnan(at)
        fill = (yy >= height * s) & (yy <= y1 * s) & known
        fade = np.clip(1 - (yy - height * s) / ((y1 - y0) * s), 0.15, 1) * 0.45
        sub = np.s_[:, cols[0] : cols[-1] + 1]
        region = f.px[sub]
        a = np.where(fill, fade, 0)[..., None]
        region += (colours[None, :, :] - region) * a
        edge = (np.abs(yy - height * s) <= 1.5 * s) & known
        f.light[sub] += colours[None] * edge[..., None] * 0.6
        region += (colours[None, :, :] - region) * edge[..., None]
        return f.finish()
