"""Designs for coding agents: a pool's quota, sessions working, a session waiting for you."""

from __future__ import annotations

import colorsys
import math
from collections.abc import Hashable

from ..readings import Snapshot
from .base import Design, rnd
from .colour import NEEDS_YOU, QUOTA_RGB, Theme, lerp
from .frame import Pixels, Still, disc, glow_disc
from .geometry import on_circle
from .motion import Eased


def agents(r: Snapshot) -> tuple[int, bool]:
    """(sessions working, whether one waits for you): none while the agents' readings are missing."""
    return r.count("working"), r.flag("waiting")


def pulse(now: float) -> float:
    """A wait's pulse, 0-1, every 1.4 s."""
    return 0.5 + 0.5 * math.cos(now * 2 * math.pi / 1.4)


def sessions(n: int) -> str:
    return f"{n} AGENT{'S' if n > 1 else ''}"


class Quota(Design):
    name = "quota"
    shows = "An agent pool's quota left, agent sessions working, a wait for you"
    about = (
        "The agents' quota as a big coral fuel gauge, one dot per working session circling inside it, and the "
        "whole screen pulsing magenta while a session waits for you."
    )
    fps = 20
    previews = ("busy", "idle", "waiting")

    working: int  # set by update(), with waiting and title
    waiting: bool
    title: str

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.quota = Eased(0.5, tau=0.4)
        self.spin = self.pulse = 0.0

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.quota.step(r.number("quota"), dt)
        self.title = r.label("quota") or "QUOTA"
        self.working, self.waiting = working, waiting = agents(r)
        self.spin = (self.spin + dt * 40) % 360
        self.pulse = pulse(now) if waiting else 0.0
        still = rnd(self.quota.value, 2), working, waiting, round(self.pulse * 10)
        return still, self.animating(now) if working else None

    def still(self) -> Still:
        waiting, q = self.waiting, self.quota.get()
        accent = lerp(self.theme.track, NEEDS_YOU, 0.35 + 0.65 * self.pulse) if waiting else QUOTA_RGB
        f = self.frame(accent if waiting or q is not None else None, 0.12 if waiting else 0.07)
        ring = self.kit.ring(166, 190)
        f.paint(ring, ring.arc(1.0), self.theme.track, glow=0)
        if q is not None:
            f.paint(ring, ring.arc(q / 100), accent)
        self.label(f, self.title)
        f.number(246, q, "%", glow=QUOTA_RGB)
        if waiting:
            self.line(f, "NEEDS YOU", rgb=lerp(self.theme.dim, NEEDS_YOU, 0.4 + 0.6 * self.pulse), size=30, spacing=2)
        elif self.working:
            self.line(f, sessions(self.working), size=30, spacing=2)
        else:
            self.line(f, "WEEK LEFT", rgb=self.theme.dim, size=30, spacing=2)
        return f.finish()

    def moving(self, px: Pixels, now: float) -> None:
        n = self.working
        for i in range(min(n, 8)):
            x, y = on_circle(146, self.spin + i * 360 / n)
            r, g, b = (255 * c for c in colorsys.hsv_to_rgb((self.spin / 360 + i / n) % 1, 0.7, 1))
            glow_disc(px, self.kit, x, y, 9, (r, g, b), 0.35)
            disc(px, self.kit, x, y, 5.5, (r, g, b))
