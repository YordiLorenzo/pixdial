"""One panel and the design it shows."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..designs import Design, Pixels, Still, with_text
from ..designs.frame import TextLayer
from ..designs.geometry import F32
from ..devices import Device
from ..readings import Snapshot
from .backdrop import DECODE, MEMORY, Backdrop, Pictures
from .report import Report
from .sender import Sender

MAX_FPS = 30  # frames a second at most: a moving part, a fade
STILL_FPS = 10  # times a second at most that a still part is drawn again: ticks this often while nothing moves
EARLY = 0.001  # s: a tick this close before a deadline counts as on time (a wait can end a little early)
RESEND = 30  # s: a frame goes out again this often even when nothing changed, so a panel that reset gets one
FADE = 0.4  # s a new design takes to fade in over the last frame

Frame8 = NDArray[np.uint8]


@dataclass(frozen=True)
class Part:
    """A still part as the screen keeps it. done: finished with its text, for a moving part that keeps clear of the
    text. Over an animated backdrop: over, what goes over each of its frames, and bare, how much of the frame shows
    (with the text in both when the moving part keeps clear of it)."""

    still: Still
    done: Frame8 | None = None
    over: F32 | None = None
    bare: F32 | None = None


class Screen:
    """A design on a panel. The still part is drawn again only when its key changes; the moving part is painted over
    a copy of it at the design's own rate. A backdrop goes under the design: a still picture in the still part, each
    frame of an animated one under the cached still part. The frames go to the panel's sender. Each tick sets when
    the next is due, at the rate the design needs now and at most max_fps a second."""

    design: Design | None = None  # set by use() once a design starts
    frame: Image.Image  # the last frame drawn, faded in; set by the first tick that draws

    def __init__(
        self,
        name: str,
        device: Device,
        report: Report,
        clock: Callable[[], float] = time.monotonic,
        max_fps: float = MAX_FPS,
        backdrop: Backdrop | None = None,
    ) -> None:
        self.name, self.report, self.max_fps, self.backdrop = name, report, max_fps, backdrop
        self.pictures: Pictures | None = None  # the backdrop at the design's size
        self.sender = Sender(name, device, report, clock)
        self.opened = 0  # the sender's opens when this screen last drew a whole frame
        self.asked: str | None = None  # the design the layout asks for
        self.spec: str | None = None  # the design shown
        self.still: Part | None = None  # None: draw it on the next tick
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
        self.pictures = self.load(design)
        self.fade_from, self.fade_start = self.shown, None  # fades from the last frame, starting with the next
        self.due = -math.inf  # at once

    def load(self, design: Design) -> Pictures | None:
        """The backdrop's frames at the size the design draws at; None without a backdrop, or with one that fails to
        decode (the design shows without it)."""
        if self.backdrop is None:
            return None
        try:
            pictures = self.backdrop.at(design.kit.size)
        except Exception as error:  # a file that broke after it was checked, or that Pillow can't decode
            self.report(f"{self.name} backdrop", error)
            return None
        self.report(f"{self.name} backdrop")
        if pictures is not self.pictures and len(pictures.frames) < pictures.total:
            self.report.log.info(
                f"{self.name} backdrop: the first {len(pictures.frames)} of its {pictures.total} frames play; a "
                f"backdrop keeps {MEMORY // 1_000_000} MB of frames and decodes {DECODE // 1_000_000} Mpx at most"
            )
        return pictures

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
            pictures = self.pictures
            key = (moving_key, pictures.index(now)) if pictures is not None and pictures.animated else moving_key
            fresh = self.render(still_key, key, now)
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
        while only an animated backdrop moves, its own rate, at most the design's; STILL_FPS for a still part that
        may change with the readings."""
        assert self.design is not None  # step() asks only with a design
        if self.fade_from is not None:
            return MAX_FPS
        fps = min(max(self.design.fps or MAX_FPS, STILL_FPS), MAX_FPS)
        if moving_key is not None:
            return fps
        if self.pictures is not None and self.pictures.animated:
            return min(max(self.pictures.fps, STILL_FPS), fps)
        return STILL_FPS

    def render(self, still_key: Hashable, moving_key: Hashable, now: float) -> bool:
        """Whether there is a new frame: the still part drawn again if its key changed (and the rate allows), the
        moving part painted over it if either changed or a fade is under way."""
        design, still, redraw = self.design, self.still, False
        assert design is not None  # tick() draws only with a design
        if still is None or (still_key != self.still_key and now - self.still_at >= 1 / STILL_FPS):
            still, redraw = draw(design, self.pictures), True
        if not (redraw or moving_key != self.moving_key or self.fade_from is not None):
            return False
        picture = None if self.pictures is None else self.pictures.frames[self.pictures.index(now)]
        shown = compose(design, still, now, picture)
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


def draw(design: Design, pictures: Pictures | None) -> Part:
    """The design's still part, over the backdrop when it has one and the design says where its background shows."""
    px, text, bare = Still(*design.still())
    if pictures is None or bare is None:
        return finished(design, px, text)
    background = design.kit.background(design.theme)
    if not pictures.animated:
        return finished(design, px + (pictures.frames[0] - background) * bare, text)
    over = px - background * bare
    if not design.under_text:  # the text goes over each frame with the rest of the still part
        bare = bare.copy()
        for rgb, box, a in text:
            over[box] += (np.array(rgb, np.float32) - over[box]) * a
            bare[box] *= 1 - a
    return Part(Still(px, text), over=over, bare=bare)


def finished(design: Design, px: F32, text: list[TextLayer]) -> Part:
    # Moving parts clear of the text go straight onto the finished 8-bit picture: about 1 ms a frame
    return Part(Still(px, text), None if design.under_text else np.asarray(with_text(px.copy(), text)))


def compose(design: Design, part: Part, now: float, picture: Frame8 | None) -> Frame8:
    """The design's frame: its moving part over a copy of the still part, or over the still part over the
    backdrop's picture for now."""
    if part.over is not None and part.bare is not None and picture is not None:
        frame: Pixels = np.multiply(picture, part.bare, dtype=np.float32)
        frame += part.over
        if not design.under_text:  # the text is in over already
            frame = np.clip(frame, 0, 255, out=frame).astype(np.uint8)
    else:
        frame = (part.still.px if part.done is None else part.done).copy()
    design.moving(frame, now)
    return frame if frame.dtype == np.uint8 else np.asarray(with_text(frame, part.still.text))
