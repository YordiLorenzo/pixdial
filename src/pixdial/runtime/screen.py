"""One panel and the design it shows."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Hashable

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..designs import Design, Pixels, Still, with_text
from ..devices import Device
from ..readings import Snapshot
from .report import Report
from .sender import Sender

MAX_FPS = 30  # frames a second at most: a moving part, a fade
STILL_FPS = 10  # times a second at most that a still part is drawn again: ticks this often while nothing moves
EARLY = 0.001  # s: a tick this close before a deadline counts as on time (a wait can end a little early)
RESEND = 30  # s: a frame goes out again this often even when nothing changed, so a panel that reset gets one
FADE = 0.4  # s a new design takes to fade in over the last frame

Frame8 = NDArray[np.uint8]
Cached = tuple[Still, Frame8 | None]  # a still part, and it finished with its text when the moving part keeps clear


class Screen:
    """A design on a panel. The still part is drawn again only when its key changes; the moving part is painted over
    a copy of it at the design's own rate. The frames go to the panel's sender. Each tick sets when the next is due,
    at the rate the design needs now and at most max_fps a second."""

    design: Design | None = None  # set by use() once a design starts
    frame: Image.Image  # the last frame drawn, faded in; set by the first tick that draws

    def __init__(
        self,
        name: str,
        device: Device,
        report: Report,
        clock: Callable[[], float] = time.monotonic,
        max_fps: float = MAX_FPS,
    ) -> None:
        self.name, self.report, self.max_fps = name, report, max_fps
        self.sender = Sender(name, device, report, clock)
        self.opened = 0  # the sender's opens when this screen last drew a whole frame
        self.asked: str | None = None  # the design the layout asks for
        self.spec: str | None = None  # the design shown
        self.still: Cached | None = None  # None: draw it on the next tick
        self.still_key: Hashable = None
        self.moving_key: Hashable = None
        self.shown: Frame8 | None = None  # the design's last frame
        self.fade_from: Frame8 | None = None
        self.fade_start: float | None = None
        self.still_at = self.sent_at = -math.inf
        self.due = -math.inf  # when it next ticks
        self.ticked: float | None = None  # when it last ticked

    def use(self, spec: str, make: Callable[[str], Design]) -> None:
        if spec == self.asked:
            return
        self.asked = spec  # a design that fails as it starts is tried again when the layout or rotation comes back
        try:
            design = make(spec)
        except Exception as error:  # a plugin design's bug: the panel keeps the design it shows
            self.report(f"{self.name} design {spec}", error)
            return
        self.spec, self.design, self.still = spec, design, None
        self.fade_from, self.fade_start = self.shown, None  # fades from the last frame, starting with the next
        self.due = -math.inf  # at once

    def tick(self, r: Snapshot, now: float) -> None:
        """Draws and posts what changed, and sets when it is next due. The deadlines lie on a grid at the rate, so a
        late tick takes the next one and the frames after it keep their pace: a missed frame is skipped, not caught
        up."""
        dt, self.ticked = 0.0 if self.ticked is None else now - self.ticked, now
        fps = min(self.step(r, now, dt), self.max_fps)
        self.due = after(now + EARLY, fps)

    def step(self, r: Snapshot, now: float, dt: float) -> float:
        """Returns the frames a second it needs now."""
        if self.design is None:  # its first design failed as it started: nothing to show yet
            return STILL_FPS
        sender = self.sender
        try:
            still_key, moving_key = self.design.update(r, now, dt)
            if not sender.open:  # nothing to draw for until it opens
                return self.rate(moving_key)
            if sender.opens != self.opened:  # it opened again: a whole frame for it at once
                self.opened, self.still = sender.opens, None
            fresh = self.render(still_key, moving_key, now)
        except Exception as error:  # a design's bug, or a reading it can't draw: the other panels go on
            self.report(f"{self.name} design {self.spec}", error)
            return STILL_FPS
        self.report(f"{self.name} design {self.spec}")
        if fresh or now - self.sent_at >= RESEND:
            sender.post(self.frame)
            self.sent_at = now
        return self.rate(moving_key)

    def rate(self, moving_key: Hashable) -> float:
        """MAX_FPS while a new design fades in; the design's fps while it moves (MAX_FPS for one that gives none);
        STILL_FPS for a still part that may change with the readings."""
        assert self.design is not None  # step() asks only with a design
        if self.fade_from is not None:
            return MAX_FPS
        if moving_key is None:
            return STILL_FPS
        return min(max(self.design.fps or MAX_FPS, STILL_FPS), MAX_FPS)

    def render(self, still_key: Hashable, moving_key: Hashable, now: float) -> bool:
        """Whether there is a new frame: the still part drawn again if its key changed (and the rate allows), the
        moving part painted over it if either changed or a fade is under way."""
        design, still, redraw = self.design, self.still, False
        assert design is not None  # tick() draws only with a design
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


def after(t: float, fps: float) -> float:
    """The first tick after t at fps. Ticks lie halfway between the moments a design's moving key changes
    (int(now * fps)), so a tick a little early or late still gets the next key."""
    return (math.floor(t * fps + 0.5) + 0.5) / fps


def draw(design: Design) -> Cached:
    px, text = design.still()[:2]
    # Moving parts clear of the text go straight onto the finished 8-bit picture: about 1 ms a frame
    return Still(px, text), None if design.under_text else np.asarray(with_text(px.copy(), text))


def compose(design: Design, still: Cached, now: float) -> Frame8:
    """The design's frame: its moving part over a copy of the still part."""
    (px, text, _), done = still
    frame: Pixels = (px if done is None else done).copy()
    design.moving(frame, now)
    return np.asarray(with_text(frame, text)) if done is None else frame
