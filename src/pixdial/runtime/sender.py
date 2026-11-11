"""Each panel's own thread, so a panel that hangs holds up only itself."""

from __future__ import annotations

import contextlib
import logging
import math
import threading
import time
from collections.abc import Callable

from PIL import Image

from ..devices import Device
from .report import Report

log = logging.getLogger(__name__)

# s: the wait before the next try to open a panel that failed (unplugged, held by another program, or not back yet
# after a resume), doubled for each failure in a row up to RETRY_MAX
RETRY_FIRST, RETRY_MAX = 0.2, 10.0


class Sender:
    """Keeps a panel open and sends it the newest frame the screen posted: one frame waits at most, and a newer one
    replaces it. After a failed open or send it closes the panel and tries again after a wait that doubles from
    RETRY_FIRST to RETRY_MAX; after a resume, or once the panel has worked for RETRY_MAX seconds, the waits start
    over."""

    def __init__(self, name: str, device: Device, report: Report, clock: Callable[[], float] = time.monotonic) -> None:
        self.name, self.device, self.report, self.clock = name, device, report, clock
        self.changed = threading.Condition()  # guards frame and the requests
        self.frame: Image.Image | None = None
        self.reopening = self.stopping = False
        self.open = False
        self.opens = 0  # times it opened; the screen draws a whole frame for each
        self.info = ""  # what the panel said as it opened, logged with the first frame it takes
        self.shown = False  # a frame went out since it opened
        self.opened_at = self.retry_at = -math.inf
        self.wait = 0.0  # the last wait before a try to open it; 0: none since it worked
        self.thread = threading.Thread(target=self.run, daemon=True, name=f"panel {name}")

    def post(self, frame: Image.Image) -> None:
        with self.changed:
            self.frame = frame
            self.changed.notify()

    def reopen(self) -> None:
        """After a resume from sleep: the panel may have come back as a new USB device."""
        with self.changed:
            self.reopening = True
            self.changed.notify()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        """Ends the thread; the panel goes dark first."""
        with self.changed:
            self.stopping = True
            self.changed.notify()

    def run(self) -> None:
        while True:
            with self.changed:
                self.changed.wait_for(self.due, None if self.open else max(0.0, self.retry_at - self.clock()))
                if self.stopping:
                    break
            self.step()
        if self.open:
            with contextlib.suppress(OSError):  # a panel that went away is dark already
                self.device.off()
            self.close()

    def due(self) -> bool:
        if self.stopping or self.reopening:
            return True
        return self.frame is not None if self.open else self.clock() >= self.retry_at

    def step(self) -> None:
        """What is due now: closing the panel for a resume, opening it, sending it the waiting frame."""
        with self.changed:
            frame, self.frame = self.frame, None
            reopening, self.reopening = self.reopening, False
        if reopening:
            self.close()
            self.retry_at, self.wait = -math.inf, 0.0  # at once
        if not self.open and (self.clock() < self.retry_at or not self.connect()):
            return
        if frame is None:
            return
        try:
            self.device.show(frame)
        except Exception as error:  # OSError: unplugged, re-enumerated after a sleep, or another program took it;
            # anything else: a frame the driver can't take, or its bug. Opened again either way
            self.failed(error)
            return
        if not self.shown:
            self.shown = True
            self.report(f"{self.name} panel", info=self.info)

    def connect(self) -> bool:
        try:
            self.info = self.device.open()
        except Exception as error:  # another program has it, it is gone, or the driver's bug
            self.failed(error)
            return False
        self.open, self.shown, self.opened_at = True, False, self.clock()
        self.opens += 1
        return True

    def failed(self, error: Exception) -> None:
        self.report(f"{self.name} panel", error)
        worked = self.open and self.shown and self.clock() - self.opened_at >= RETRY_MAX
        self.close()
        self.wait = RETRY_FIRST if worked or not self.wait else min(2 * self.wait, RETRY_MAX)
        self.retry_at = self.clock() + self.wait
        log.debug("next try in %.1f s", self.wait)

    def close(self) -> None:
        if self.open:
            self.device.close()
        self.open = False
