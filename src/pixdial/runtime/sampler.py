"""Sampling every source in a thread of its own, so a slow sensor never holds up a frame."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from ..readings import Reading
from ..sources import Source
from .report import Report


class Sampler:
    """Reads each source every period seconds, each in a thread of its own, so a slow source holds up neither the
    frames nor the other sources. fresh() hands over the readings that are fresh now, a later source in the list
    winning a key two report; one that hasn't come for its source's stale_after seconds is left out."""

    def __init__(
        self,
        sources: Sequence[tuple[str, Source]],
        report: Report,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sources, self.report, self.clock = sources, report, clock
        # each source's readings by key with when each came; a source's dict is replaced whole, so fresh() needs no lock
        self.values: list[dict[str, tuple[Reading, float]]] = [{} for _ in sources]
        self.resets = [False for _ in sources]
        self.stopping = threading.Event()

    def start(self) -> None:
        for i, (name, _) in enumerate(self.sources):
            threading.Thread(target=self.run, args=(i,), daemon=True, name=name).start()

    def run(self, i: int) -> None:
        source = self.sources[i][1]
        while not self.stopping.is_set():
            if self.resets[i]:
                self.resets[i] = False
                source.reset()
            started = self.clock()
            self.sample(i)
            self.stopping.wait(max(0.0, started + source.period - self.clock()))
        source.close()

    def sample(self, i: int) -> None:
        name, source = self.sources[i]
        try:
            readings = source.read()
        except Exception as error:  # a broken source must not stop the others
            self.report(name, error if isinstance(error, OSError | ValueError) else repr(error))
            return
        self.report(name)
        now = self.clock()
        self.values[i] = {**self.values[i], **{k: (r, now) for k, r in readings.items()}}

    def fresh(self, now: float) -> dict[str, Reading]:
        out = {}
        for (_, source), values in zip(self.sources, self.values, strict=True):
            out.update({k: r for k, (r, at) in values.items() if now - at < source.stale_after})
        return out

    def resumed(self) -> None:
        """The machine slept: the readings from before are dropped (the monotonic clock didn't count the sleep, so
        they would look fresh), and the sources drop their handles before their next read."""
        self.values = [{} for _ in self.sources]
        self.resets = [True for _ in self.sources]

    def stop(self) -> None:
        self.stopping.set()
