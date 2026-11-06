"""Devices: the panels frames go to. A driver opens one panel, shows pictures on it and turns it dark."""

from .base import Device, Found
from .png import Png
from .slv3 import Slv3

BUILTIN: dict[str, type[Device]] = {"slv3": Slv3, "png": Png}

__all__ = ["BUILTIN", "Device", "Found", "Png", "Slv3"]
