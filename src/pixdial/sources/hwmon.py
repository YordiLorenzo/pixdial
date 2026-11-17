"""Readings from Linux hwmon sensors (/sys/class/hwmon), with the limits the chips report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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

    def gives(self) -> frozenset[str]:
        """Its keys, whether their sensors are there yet or not (a GPU's hwmon node can come after the service)."""
        return frozenset(self.sensors)

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
        return reading(self.paths[key])

    def find(self, key: str) -> list[Path]:
        chips: dict[str, list[Path]] = {}
        for d in sorted(self.root.glob("hwmon*")):
            chips.setdefault(read(d / "name"), []).append(d)  # one per CPU socket for coretemp
        found = [f for name in self.sensors[key] for f in sensor(chips, *name.split("/"))]
        if not found:
            raise FileNotFoundError(f"{key}: no hwmon sensor {' or '.join(self.sensors[key])}")
        return found


@dataclass(frozen=True)
class Sensor:
    name: str  # file stem for an input, full file name for an average
    label: str
    reading: Reading | None


def scan(root: Path) -> list[tuple[str, list[Sensor]]]:
    """Every chip and input, including voltages and unavailable sensors; read-only."""
    found = []
    for d in sorted(root.glob("hwmon*")):
        try:
            name = read(d / "name")
        except OSError:
            continue
        sensors = []
        for f in sorted([*d.glob("*_input"), *d.glob("*_average")]):
            stem, _, kind = f.name.rpartition("_")
            try:
                label = read(f.with_name(f"{stem}_label"))
            except OSError:
                label = stem
            try:
                value = reading([f])
            except (OSError, ValueError):  # a sensor that is off now
                value = None
            sensors.append(Sensor(stem if kind == "input" else f.name, label, value))
        found.append((name, sensors))
    return found


def chips(root: Path = HWMON) -> list[tuple[str, dict[str, Reading]]]:
    """Readable sensors by label for doctor reports, without voltages."""
    return [
        (
            chip,
            {
                s.label + (" average" if s.name.endswith("_average") else ""): s.reading
                for s in sensors
                if s.reading is not None and s.reading.unit != "V"
            },
        )
        for chip, sensors in scan(root)
    ]


def reading(inputs: Sequence[Path]) -> Reading:
    kind = inputs[0].name.rpartition("_")[0].rstrip("0123456789")
    unit, scale = UNITS.get(kind, ("", 1.0))
    value = max(int(read(f)) for f in inputs) / scale
    return Reading(value, unit, max=limit(inputs, scale))


def sensor(chips: Mapping[str, list[Path]], chip: str, name: str) -> list[Path]:
    """Inputs by stem or label, or averages by full file name, on every chip of that name."""
    found = []
    for d in chips.get(chip, []):
        direct = d / (name if name.endswith("_average") else f"{name}_input")
        if direct.exists():
            found.append(direct)
        found += [f.with_name(f.name.replace("_label", "_input")) for f in d.glob("*_label") if read(f) == name]
    return found


def limit(inputs: Sequence[Path], scale: float) -> float | None:
    """The lowest crit, else max, that the sensors report."""
    for kind in ("_crit", "_max"):
        files = []
        for f in inputs:
            average = f.with_name(f.name + kind)
            files.append(
                average
                if f.name.endswith("_average") and average.exists()
                else f.with_name(f.name.rpartition("_")[0] + kind)
            )
        found = [int(read(f)) / scale for f in files if f.exists()]
        if found:
            return min(found)
    return None


def read(path: Path) -> str:
    return path.read_text().strip()
