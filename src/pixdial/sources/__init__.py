"""Sources: where readings come from. The runtime calls each source's read() every period seconds, in a thread of
its own, so a slow one never holds up a frame."""

from ..readings import Reading
from .base import Source
from .command import Command
from .cpu import Cpu, Rapl
from .hwmon import Hwmon
from .nvml import Nvml

BUILTIN: dict[str, type[Source]] = {"cpu": Cpu, "rapl": Rapl, "hwmon": Hwmon, "nvml": Nvml, "command": Command}

__all__ = ["BUILTIN", "Command", "Cpu", "Hwmon", "Nvml", "Rapl", "Reading", "Source"]
