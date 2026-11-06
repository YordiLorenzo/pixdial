"""One panel and the design it shows."""

from __future__ import annotations

import math
from collections.abc import Callable, Hashable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..designs import Design, Pixels, Still, with_text
from ..devices import Device
from ..readings import Snapshot
from .report import Report

STILL_FPS = 10  # times a second at most that a still part is drawn again
RESEND = 30  # s: a frame goes out again this often even when nothing changed, so a panel that reset gets one
FADE = 0.4  # s a new design takes to fade in over the last frame
RETRY = 10  # s between tries to open a panel that couldn't be opened

Frame8 = NDArray[np.uint8]
Cached = tuple[Still, Frame8 | None]  # a still part, and it finished with its text when the moving part keeps clear


class Screen:
    """A design on a panel. The still part is drawn again only when its key changes; the moving part is painted over
    a copy of it at the design's own rate."""

    design: Design  # set by use()
    frame: Image.Image  # the last frame sent, faded in; set by the first tick that sends

    def __init__(self, name: str, device: Device, report: Report) -> None:
        self.name, self.device, self.report = name, device, report
        self.open = False
        self.spec: str | None = None
        self.still: Cached | None = None  # None: draw it on the next tick
        self.still_key: Hashable = None
        self.moving_key: Hashable = None
        self.shown: Frame8 | None = None  # the design's last frame
        self.fade_from: Frame8 | None = None
        self.fade_start: float | None = None
        self.still_at = self.sent_at = self.retry_at = -math.inf

    def use(self, spec: str, make: Callable[[str], Design]) -> None:
        if spec != self.spec:
            self.spec, self.design, self.still = spec, make(spec), None
            self.fade_from, self.fade_start = self.shown, None  # fades from the last frame, starting with the next

    def tick(self, r: Snapshot, now: float, dt: float) -> bool:
        """Returns whether it animates, so the loop knows how soon to come back."""
        try:
            still_key, moving_key = self.design.update(r, now, dt)
            if not self.open and not self.connect(now):
                return moving_key is not None
            fresh = self.render(still_key, moving_key, now)
        except Exception as error:  # a design's bug, or a reading it can't draw: the other panels go on
            self.report(f"{self.name} design {self.spec}", repr(error))
            return False
        self.report(f"{self.name} design {self.spec}")
        if fresh or now - self.sent_at >= RESEND:
            self.send(now)
        return moving_key is not None or self.fade_from is not None

    def render(self, still_key: Hashable, moving_key: Hashable, now: float) -> bool:
        """Whether there is a new frame: the still part drawn again if its key changed (and the rate allows), the
        moving part painted over it if either changed or a fade is under way."""
        design, still, redraw = self.design, self.still, False
        if still is None or (still_key != self.still_key and now - self.still_at >= 1 / STILL_FPS):
            still, redraw = draw(design), True
        if not (redraw or moving_key != self.moving_key or self.fade_from is not None):
            return False
        shown = compose(design, still, now)
        # Kept only once the whole frame is drawn, so a design that fails halfway is drawn afresh next time
        if redraw:
            self.still, self.still_key, self.still_at = still, still_key, now
        self.shown, self.moving_key = shown, moving_key
        self.frame = Image.fromarray(self.blend(shown, now))
        return True

    def send(self, now: float) -> None:
        try:
            self.device.show(self.frame)
            self.sent_at = now
        except OSError as error:  # unplugged, re-enumerated after a sleep, or another program took it
            self.report(f"{self.name} panel", error)
            self.close()

    def connect(self, now: float) -> bool:
        if now < self.retry_at:
            return False
        try:
            info = self.device.open()
        except OSError as error:  # another program has it, or it is gone
            self.retry_at = now + RETRY
            self.report(f"{self.name} panel", error)
            return False
        self.open, self.still = True, None  # a fresh frame for it at once
        self.report(f"{self.name} panel", info=info)
        return True

    def blend(self, shown: Frame8, now: float) -> Frame8:
        """While a new design fades in, the last design's frame under it."""
        if self.fade_from is None:
            return shown
        if self.fade_start is None:
            self.fade_start = now
        t = (now - self.fade_start) / FADE
        if t >= 1:
            self.fade_from = None
            return shown
        return (self.fade_from * (1 - t) + shown * t).astype(np.uint8)

    def close(self) -> None:
        if self.open:
            self.device.close()
        self.open = False

    def off(self) -> None:
        """Dark when the program stops."""
        if self.open:
            self.device.off()


def draw(design: Design) -> Cached:
    px, text = design.still()
    # Moving parts clear of the text go straight onto the finished 8-bit picture: about 1 ms a frame
    return (px, text), None if design.under_text else np.asarray(with_text(px.copy(), text))


def compose(design: Design, still: Cached, now: float) -> Frame8:
    """The design's frame: its moving part over a copy of the still part."""
    (px, text), done = still
    frame: Pixels = (px if done is None else done).copy()
    design.moving(frame, now)
    return np.asarray(with_text(frame, text)) if done is None else frame
