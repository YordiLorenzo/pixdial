"""The loop that keeps every panel showing its design."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Sequence

from .. import NAME, __version__
from .feed import Feed
from .layout import Catalog, Layout
from .report import Report
from .sampler import Sampler
from .screen import EARLY, Screen, after

STOP_WAIT = 5  # s the panels get to go dark when it stops: a hung one's USB calls time out within about 4
BOOTTIME = getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)  # Linux's counts time asleep

log = logging.getLogger(__name__)


class Clock:
    """The clocks the runner reads; tests give it a fake one."""

    def monotonic(self) -> float:
        return time.monotonic()

    def boottime(self) -> float:
        return time.clock_gettime(BOOTTIME)

    def wall(self) -> float:
        return time.time()


class Runner:
    """Each tick: notices a resume from sleep and a new layout, puts each panel's design for now on it, and gives
    every screen that is due the same snapshot of the readings. It sleeps until the next screen is due."""

    def __init__(
        self,
        screens: Sequence[Screen],
        sampler: Sampler,
        feed: Feed,
        catalog: Catalog,
        layout: Layout,
        report: Report,
        clock: Clock | None = None,
    ) -> None:
        self.screens, self.sampler, self.feed, self.catalog, self.layout = screens, sampler, feed, catalog, layout
        self.report, self.clock = report, clock or Clock()
        self.specs = layout.default
        self.stamp: float | None = math.nan  # the layout file not read yet
        self.asleep = self.clock.boottime() - self.clock.monotonic()  # time spent asleep so far

    def run(self, stop: threading.Event) -> None:
        """Until stop is set; the panels go dark at the end."""
        panels = ", ".join(f"{s.name} ({type(s.sender.device).__name__})" for s in self.screens)
        sources = ", ".join(name for name, _ in self.sampler.sources)
        log.info("%s %s: panels %s; sources %s", NAME, __version__, panels, sources or "none")
        self.sampler.start()
        for screen in self.screens:
            screen.sender.thread.start()
        try:
            while not stop.is_set():
                stop.wait(self.tick())
        finally:
            self.sampler.stop()
            for screen in self.screens:
                screen.sender.stop()
            deadline = time.monotonic() + STOP_WAIT
            for screen in self.screens:
                screen.sender.thread.join(max(0.0, deadline - time.monotonic()))

    def tick(self) -> float:
        """A frame for every panel that is due; returns the seconds until the next is due."""
        now = self.clock.monotonic()
        was, self.asleep = self.asleep, self.clock.boottime() - now
        if self.asleep - was > 1:  # a resume: the panels may have come back as new USB devices
            for screen in self.screens:
                screen.sender.reopen()
            self.sampler.resumed()
        self.follow_layout()
        for screen, spec in zip(self.screens, self.layout.showing(self.specs, self.clock.wall()), strict=True):
            screen.use(spec, self.catalog.make)
        snapshot = self.feed.snapshot(self.sampler.fresh(now), now, self.clock.wall())
        for screen in self.screens:
            if screen.due <= now + EARLY:
                screen.tick(snapshot, now)
        due = min(screen.due for screen in self.screens)
        if self.feed.fps:  # also on the shortest trail's grid, so a panel's low max_fps does not thin out the history
            due = min(due, after(now + EARLY, self.feed.fps))
        return max(0.0, due - self.clock.monotonic())

    def follow_layout(self) -> None:
        try:
            stamp = self.layout.stamp()
            if stamp != self.stamp:
                self.stamp = stamp  # a bad file is reported once, not read again until it changes
                self.specs = self.layout.load()
                self.report("layout", designs=" ".join(self.specs))
        except (OSError, ValueError) as error:  # a layout file edited by hand to a bad name: keep the designs
            self.report("layout", f"{self.layout.path}: {error}")
