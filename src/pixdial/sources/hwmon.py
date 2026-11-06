"""Readings from Linux hwmon sensors (/sys/class/hwmon), with the limits the chips report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..readings import Reading
from .base import Source

HWMON = Path("/sys/class/hwmon")
UNITS = {"temp": ("°C", 1e3), "power": ("W", 1e6), "fan": ("rpm", 1.0), "in": ("V", 1e3), "curr": ("A", 1e3)}


class Hwmon(Source):
    """readings: a reading key for each sensor, named "chip/sensor": the chip's hwmon name and the sensor's label or
    file name (k10temp/Tctl, corsairpsu/power1). A list gives the highest of the sensors found, so a key can name
    the alternatives on different machines (k10temp/Tctl, coretemp/Package id 0) or several sensors of one part.
    Each reading's limit is the lowest crit (else max) its sensors report."""

    def __init__(self, readings: Mapping[str, str | Sequence[str]], root: str = str(HWMON)) -> None:
        self.root = Path(root)
        self.sensors = {key: [names] if isinstance(names, str) else list(names) for key, names in readings.items()}
        for key, names in self.sensors.items():
            for name in names:
                if name.count("/") != 1:
                    raise ValueError(f"{key}: {name!r} is not chip/sensor")
        self.paths: dict[str, list[Path]] = {}  # key -> its sensors' input files, found once

    def read(self) -> dict[str, Reading]:
        """The readings it can read now; raises only when it can read none."""
        out, errors = {}, []
        for key in self.sensors:
            try:
                out[key] = self.reading(key)
            except (OSError, ValueError) as error:
                self.paths.pop(key, None)  # look it up again: hwmon numbers change when a device comes back
                errors.append(error)
        if errors and not out:
            raise errors[0]
        return out

    def reset(self) -> None:
        self.paths.clear()  # after a resume a hwmon number may belong to another device

    def reading(self, key: str) -> Reading:
        if key not in self.paths:
            self.paths[key] = self.find(key)
        inputs = self.paths[key]
        kind = inputs[0].name.removesuffix("_input").rstrip("0123456789")
        unit, scale = UNITS.get(kind, ("", 1.0))
        value = max(int(read(f)) for f in inputs) / scale
        return Reading(value, unit, max=limit(inputs, scale))

    def find(self, key: str) -> list[Path]:
        chips: dict[str, list[Path]] = {}
        for d in sorted(self.root.glob("hwmon*")):
            chips.setdefault(read(d / "name"), []).append(d)  # one per CPU socket for coretemp
        found = [f for name in self.sensors[key] for f in sensor(chips, *name.split("/"))]
        if not found:
            raise FileNotFoundError(f"{key}: no hwmon sensor {' or '.join(self.sensors[key])}")
        return found


def sensor(chips: Mapping[str, list[Path]], chip: str, name: str) -> list[Path]:
    """The input files of a sensor, by file name (temp1) or label (Tctl), on every chip of that name."""
    found = []
    for d in chips.get(chip, []):
        if (d / f"{name}_input").exists():
            found.append(d / f"{name}_input")
        found += [f.with_name(f.name.replace("_label", "_input")) for f in d.glob("*_label") if read(f) == name]
    return found


def limit(inputs: Sequence[Path], scale: float) -> float | None:
    """The lowest crit, else max, that the sensors report."""
    for kind in ("_crit", "_max"):
        files = [f.with_name(f.name.replace("_input", kind)) for f in inputs]
        found = [int(read(f)) / scale for f in files if f.exists()]
        if found:
            return min(found)
    return None


def read(path: Path) -> str:
    return path.read_text().strip()
