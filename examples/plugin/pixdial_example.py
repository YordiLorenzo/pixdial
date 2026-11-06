"""A plugin with one design, one source and one device: the smallest working example of each."""

from __future__ import annotations

import os
from collections.abc import Hashable
from pathlib import Path

from PIL import Image

from pixdial.designs import LOAD, Design, Eased, Still, Theme, rnd
from pixdial.devices import Device
from pixdial.readings import Reading, Snapshot
from pixdial.sources import Source


class LoadAverage(Source):
    """loadavg: the system's one-minute load average, out of its number of CPUs."""

    period = 5.0

    def read(self) -> dict[str, Reading]:
        return {"loadavg": Reading(os.getloadavg()[0], max=os.cpu_count())}


class Big(Design):
    name = "big"
    shows = "The load average as a share of the CPUs, on a gauge"

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.share, self.cpus = Eased(1), 1.0

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        load, self.cpus = r.number("loadavg"), r.max("loadavg") or 1.0
        self.share.step(None if load is None else 100 * load / self.cpus, dt)
        return (rnd(self.share.value), self.cpus), None  # a new still part when a whole per cent changes; no motion

    def still(self) -> Still:
        value = self.share.get()
        f = self.frame(self.colour(LOAD, value))
        self.gauge(f, value, LOAD)
        self.label(f, "LOAD")
        f.number(246, value, "%")
        self.line(f, f"OF {self.cpus:.0f} CPUS")
        return f.finish()


class Folder(Device):
    """Every frame as a numbered JPEG in a folder, to make a video of a design."""

    def __init__(self, path: str) -> None:
        self.path, self.count = Path(path).expanduser(), 0

    def open(self) -> str:
        self.path.mkdir(parents=True, exist_ok=True)
        return f"writing {self.path}"

    def show(self, image: Image.Image) -> None:
        self.count += 1
        image.save(self.path / f"{self.count:06d}.jpg", quality=90)

    def off(self) -> None:
        pass

    def close(self) -> None:
        pass
