"""Fake hardware defaults for unit tests and options for the opt-in hardware test."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial.devices import usbfs
from pixdial.sources import Amdgpu, Cpu, Hwmon, Rapl, amdgpu, hwmon, nvml


@pytest.fixture(autouse=True)
def hardware_defaults(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default source and discovery paths must not inspect the machine running the unit tests."""
    if request.node.get_closest_marker("hardware"):
        return
    stat = tmp_path / "proc-stat"
    stat.write_text("cpu 100 0 100 800 0 0 0 0\ncpu0 100 0 100 800 0 0 0 0\n")
    # Change defaults on the original functions so imported aliases and explicit fixture roots still work.
    monkeypatch.setattr(Cpu.__init__, "__defaults__", (str(stat),))
    monkeypatch.setattr(Rapl.__init__, "__defaults__", (str(tmp_path / "energy_uj"),))
    monkeypatch.setattr(Hwmon.__init__, "__defaults__", (str(tmp_path / "hwmon"),))
    monkeypatch.setattr(Amdgpu.__init__, "__defaults__", (str(tmp_path / "drm"),))
    monkeypatch.setattr(amdgpu, "PCI", tmp_path / "pci")
    monkeypatch.setattr(nvml, "LIBRARY", "libnvidia-ml-not-here.so.1")
    monkeypatch.setattr(hwmon.chips, "__defaults__", (tmp_path / "hwmon",))
    monkeypatch.setattr(usbfs.attached, "__defaults__", (tmp_path / "usb",))
    monkeypatch.setattr(usbfs.products, "__defaults__", (tmp_path / "usb",))
    monkeypatch.setattr(usbfs.holder, "__defaults__", (tmp_path / "usb", tmp_path / "proc"))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware-seconds",
        type=float,
        default=600.0,
        help="how long `-m hardware` sends frames to the panels before it resets them (default 600)",
    )
