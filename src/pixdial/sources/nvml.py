"""An NVIDIA GPU through libnvidia-ml (what nvidia-smi uses, without its start-up time every read)."""

from __future__ import annotations

import ctypes
from typing import Any

from ..readings import Reading
from .base import Source

SLOWDOWN = 1  # NVML_TEMPERATURE_THRESHOLD_SLOWDOWN
LIBRARY = "libnvidia-ml.so.1"  # the NVIDIA driver's


class Nvml(Source):
    """gpu_c: temperature, its limit the slowdown point; gpu_w: board power, its limit the enforced power limit;
    gpu_use: utilisation (%). Each is left out where the GPU doesn't report it. index: which GPU."""

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.lib: Any = None
        self.dev = ctypes.c_void_p()

    def read(self) -> dict[str, Reading]:
        try:
            if self.lib is None:
                self.connect()
            out = {
                "gpu_c": Reading(
                    self.uint("nvmlDeviceGetTemperature", 0),
                    "°C",
                    max=self.optional("nvmlDeviceGetTemperatureThreshold", SLOWDOWN),
                )
            }
            power, limit = self.optional("nvmlDeviceGetPowerUsage"), self.optional("nvmlDeviceGetEnforcedPowerLimit")
            if power is not None:
                out["gpu_w"] = Reading(power / 1000, "W", max=limit and limit / 1000)
            use = (ctypes.c_uint * 2)()  # nvmlUtilization_t: gpu, memory
            if not self.lib.nvmlDeviceGetUtilizationRates(self.dev, use):  # unsupported on a MIG-split GPU
                out["gpu_use"] = Reading(use[0], "%")
            return out
        except OSError:
            self.close()  # start over next time
            raise

    def gives(self) -> frozenset[str]:
        """Its readings where the NVIDIA driver's library loads, none elsewhere."""
        try:
            ctypes.CDLL(LIBRARY)
        except OSError:
            return frozenset()
        return frozenset({"gpu_c", "gpu_w", "gpu_use"})

    def reset(self) -> None:
        self.close()  # the handle may not survive the GPU's suspend

    def close(self) -> None:
        if self.lib is not None:
            self.lib.nvmlShutdown()  # NVML counts its starts; each needs its shutdown
        self.lib = None

    def connect(self) -> None:
        lib = ctypes.CDLL(LIBRARY)
        self.check(lib.nvmlInit_v2())
        self.lib = lib
        self.check(lib.nvmlDeviceGetHandleByIndex_v2(self.index, ctypes.byref(self.dev)))

    @staticmethod
    def check(code: int) -> None:
        if code:
            raise OSError(f"NVML error {code}")

    def optional(self, call: str, *args: int) -> int | None:
        """A value some GPUs don't report (NVML_ERROR_NOT_SUPPORTED): a limit, or the power on some boards."""
        try:
            return self.uint(call, *args)
        except OSError:
            return None

    def uint(self, call: str, *args: int) -> int:
        value = ctypes.c_uint()
        self.check(getattr(self.lib, call)(self.dev, *args, ctypes.byref(value)))
        return value.value
