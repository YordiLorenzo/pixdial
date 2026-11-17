"""NVML through a fake ctypes library, with no driver or GPU required."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import pytest

from pixdial.readings import Reading
from pixdial.sources import Nvml, nvml


def uint(value: int) -> Callable[..., int]:
    def write(*args: Any) -> int:
        assert args[0].value == 42
        ctypes.cast(args[-1], ctypes.POINTER(ctypes.c_uint))[0] = value
        return 0

    return write


class Library:
    """The C entry points used by Nvml, including writes through output pointers."""

    def __init__(self) -> None:
        self.nvmlInit_v2 = Mock(return_value=0)
        self.nvmlShutdown = Mock(return_value=0)
        self.nvmlDeviceGetHandleByIndex_v2 = Mock(side_effect=self.handle)
        self.nvmlDeviceGetTemperature = Mock(side_effect=uint(67))
        self.nvmlDeviceGetTemperatureThreshold = Mock(side_effect=uint(90))
        self.nvmlDeviceGetPowerUsage = Mock(side_effect=uint(187500))
        self.nvmlDeviceGetEnforcedPowerLimit = Mock(side_effect=uint(450000))
        self.nvmlDeviceGetUtilizationRates = Mock(side_effect=self.utilization)

    @staticmethod
    def handle(index: int, result: Any) -> int:
        ctypes.cast(result, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(42)
        return 0

    @staticmethod
    def utilization(device: ctypes.c_void_p, result: Any) -> int:
        assert device.value == 42
        result[0], result[1] = 73, 12
        return 0


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Library:
    lib = Library()
    monkeypatch.setattr(ctypes, "CDLL", Mock(return_value=lib))
    return lib


def test_nvml_reads_units_limits_and_the_selected_gpu(library: Library) -> None:
    source = Nvml(index=2)
    expected = {
        "gpu_c": Reading(67, "°C", max=90),
        "gpu_w": Reading(187.5, "W", max=450),
        "gpu_use": Reading(73, "%"),
    }
    assert source.read() == expected
    assert source.read() == expected
    library.nvmlInit_v2.assert_called_once_with()
    assert library.nvmlDeviceGetHandleByIndex_v2.call_args.args[0] == 2
    assert library.nvmlDeviceGetHandleByIndex_v2.call_count == 1
    assert library.nvmlDeviceGetTemperature.call_args.args[1] == 0
    assert library.nvmlDeviceGetTemperatureThreshold.call_args.args[1] == nvml.SLOWDOWN
    source.close()
    source.close()
    library.nvmlShutdown.assert_called_once_with()


@pytest.mark.parametrize(
    "unsupported",
    [
        "nvmlDeviceGetTemperatureThreshold",
        "nvmlDeviceGetPowerUsage",
        "nvmlDeviceGetEnforcedPowerLimit",
        "nvmlDeviceGetUtilizationRates",
    ],
)
def test_nvml_keeps_supported_readings(library: Library, unsupported: str) -> None:
    call = getattr(library, unsupported)
    call.side_effect, call.return_value = None, 3  # NVML_ERROR_NOT_SUPPORTED
    expected = {
        "gpu_c": Reading(67, "°C", max=90),
        "gpu_w": Reading(187.5, "W", max=450),
        "gpu_use": Reading(73, "%"),
    }
    if unsupported == "nvmlDeviceGetTemperatureThreshold":
        expected["gpu_c"] = Reading(67, "°C")
    elif unsupported == "nvmlDeviceGetEnforcedPowerLimit":
        expected["gpu_w"] = Reading(187.5, "W")
    else:
        del expected["gpu_w" if unsupported == "nvmlDeviceGetPowerUsage" else "gpu_use"]
    source = Nvml()
    try:
        assert source.read() == expected
        library.nvmlShutdown.assert_not_called()
    finally:
        source.close()


@pytest.mark.parametrize("failed", ["nvmlInit_v2", "nvmlDeviceGetHandleByIndex_v2", "nvmlDeviceGetTemperature"])
def test_nvml_reconnects_after_a_failure(library: Library, failed: str) -> None:
    call = getattr(library, failed)
    working = call.side_effect
    call.side_effect, call.return_value = None, 15
    source = Nvml()
    with pytest.raises(OSError, match="NVML error 15"):
        source.read()
    assert source.lib is None
    assert library.nvmlShutdown.call_count == (0 if failed == "nvmlInit_v2" else 1)
    call.side_effect, call.return_value = working, 0
    assert source.read()["gpu_c"] == Reading(67, "°C", max=90)
    assert library.nvmlInit_v2.call_count == 2
    source.close()
    assert library.nvmlShutdown.call_count == (1 if failed == "nvmlInit_v2" else 2)


def test_nvml_reset_releases_the_handle_and_reconnects(library: Library) -> None:
    source = Nvml()
    source.read()
    source.reset()
    source.reset()
    library.nvmlShutdown.assert_called_once_with()
    assert source.read()["gpu_use"] == Reading(73, "%")
    assert library.nvmlDeviceGetHandleByIndex_v2.call_count == 2
    source.close()
    assert library.nvmlShutdown.call_count == 2


def test_nvml_gives_loads_the_library_without_initializing_it(library: Library) -> None:
    assert Nvml().gives() == frozenset({"gpu_c", "gpu_w", "gpu_use"})
    library.nvmlInit_v2.assert_not_called()
    library.nvmlDeviceGetHandleByIndex_v2.assert_not_called()
    library.nvmlShutdown.assert_not_called()


def test_nvml_reports_a_missing_library_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = Mock(side_effect=OSError("no NVIDIA driver"))
    monkeypatch.setattr(ctypes, "CDLL", loader)
    source = Nvml()
    assert source.gives() == frozenset()
    with pytest.raises(OSError, match="no NVIDIA driver"):
        source.read()
    assert source.lib is None
    lib = Library()
    loader.side_effect, loader.return_value = None, lib
    assert source.read()["gpu_w"] == Reading(187.5, "W", max=450)
    source.close()
    lib.nvmlShutdown.assert_called_once_with()
