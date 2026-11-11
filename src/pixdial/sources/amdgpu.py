"""An AMD GPU through the amdgpu driver's sysfs files, which every user may read (docs.kernel.org/gpu/amdgpu)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..readings import Reading
from .base import Source

DRM = Path("/sys/class/drm")
GIB = 2**30


class Amdgpu(Source):
    """gpu_c: the edge temperature, its limit the crit the card reports; gpu_w: power (power1_average, or
    power1_input where the kernel gives only that; on a processor's built-in GPU the whole chip's), its limit the
    power cap; gpu_use: gpu_busy_percent (%); gpu_vram: VRAM in use (GiB), its limit the total. Each is left out
    where the GPU doesn't report it. With several AMD GPUs it reads the one with the most VRAM, so a graphics card
    wins over the processor's GPU. With none it gives nothing, and no error. It looks for the GPU on every read:
    amdgpu can add the card and its hwmon files after pixdial starts. Experimental: tested on copies of the sysfs
    files, not yet on a card."""

    note = "experimental"

    def __init__(self, root: str = str(DRM)) -> None:
        self.root = Path(root)

    def read(self) -> dict[str, Reading]:
        """The readings it can read now; raises only when its GPU gives none."""
        device = gpu(self.root)
        if device is None:
            return {}
        sensors = min((device / "hwmon").glob("hwmon*"), default=None)  # can come after the card (lian-li-linux #214)
        out, errors = {}, []
        for key, reading in READINGS.items():
            try:
                found = reading(device, sensors)
            except (OSError, ValueError) as error:  # such as EPERM while the GPU is in runtime suspend
                errors.append(error)
                continue
            if found is not None:
                out[key] = found
        if errors and not out:
            raise errors[0]
        return out


def gpu(root: Path) -> Path | None:
    """The PCI device directory of the amdgpu card with the most VRAM, or None."""
    cards = [
        d / "device"
        for d in sorted(root.glob("card*"))  # card0, and its connectors card0-DP-1 and so on
        if d.name.removeprefix("card").isdigit() and (d / "device" / "driver").resolve().name == "amdgpu"
    ]
    return max(cards, key=lambda device: value(device / "mem_info_vram_total") or 0, default=None)


def temperature(device: Path, sensors: Path | None) -> Reading | None:
    if sensors is None:
        return None
    c = value(sensors / "temp1_input", 1e3)  # temp1 is the edge on every amdgpu card
    return None if c is None else Reading(c, "°C", max=value(sensors / "temp1_crit", 1e3))


def power(device: Path, sensors: Path | None) -> Reading | None:
    if sensors is None:
        return None
    w = value(sensors / "power1_average", 1e6)
    w = value(sensors / "power1_input", 1e6) if w is None else w
    return None if w is None else Reading(w, "W", max=value(sensors / "power1_cap", 1e6))


def use(device: Path, sensors: Path | None) -> Reading | None:
    busy = value(device / "gpu_busy_percent")
    return None if busy is None else Reading(busy, "%")


def vram(device: Path, sensors: Path | None) -> Reading | None:
    used = value(device / "mem_info_vram_used", GIB)
    return None if used is None else Reading(used, "GiB", max=value(device / "mem_info_vram_total", GIB))


READINGS: dict[str, Callable[[Path, Path | None], Reading | None]] = {
    "gpu_c": temperature,
    "gpu_w": power,
    "gpu_use": use,
    "gpu_vram": vram,
}


def value(path: Path, scale: float = 1.0) -> float | None:
    """A sysfs number, divided by scale; None where the GPU has no such file."""
    try:
        return int(path.read_text()) / scale
    except FileNotFoundError:
        return None
