"""Discovery against temporary USB, hwmon and PCI trees."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial.devices import usbfs
from pixdial.readings import Reading
from pixdial.sources import Amdgpu, amdgpu, hwmon
from tests.test_slv3 import usb_device
from tests.test_sources import chip


def test_usb_discovery_filters_ids_sorts_ports_and_formats_nodes(tmp_path: Path) -> None:
    usb_device(tmp_path, "2-4", "0005", "SECOND", 12)
    (tmp_path / "2-4" / "busnum").write_text("2\n")
    usb_device(tmp_path, "1-2", "0005", "FIRST", 3)
    usb_device(tmp_path, "1-3", "0006", "TL", 4)
    usb_device(tmp_path, "1-4", "0005", "OTHER VENDOR", 5)
    (tmp_path / "1-4" / "idVendor").write_text("1234\n")
    (tmp_path / "1-0:1.0").mkdir()
    assert usbfs.attached(0x1CBE, 0x0005, tmp_path) == [
        usbfs.UsbDevice("FIRST", "/dev/bus/usb/001/003", "1-2"),
        usbfs.UsbDevice("SECOND", "/dev/bus/usb/002/012", "2-4"),
    ]


@pytest.mark.parametrize("field", ["idVendor", "idProduct", "busnum", "devnum", "serial"])
@pytest.mark.parametrize("broken", ["missing", "invalid"])
def test_usb_discovery_ignores_incomplete_devices(tmp_path: Path, field: str, broken: str) -> None:
    usb_device(tmp_path, "1-2", "0005", "BROKEN", 3)
    usb_device(tmp_path, "1-3", "0005", "GOOD", 4)
    path = tmp_path / "1-2" / field
    path.unlink()
    if broken == "invalid":
        if field == "serial":
            path.mkdir()  # unreadable as a file
        else:
            path.write_text("not a number\n")
    assert usbfs.attached(0x1CBE, 0x0005, tmp_path) == [usbfs.UsbDevice("GOOD", "/dev/bus/usb/001/004", "1-3")]


def test_usb_discovery_handles_a_missing_tree(tmp_path: Path) -> None:
    assert usbfs.attached(0x1CBE, 0x0005, tmp_path / "absent") == []
    assert usbfs.products(0x1CBE, tmp_path / "absent") == []


def test_hwmon_discovery_labels_units_and_power_layouts(tmp_path: Path) -> None:
    chip(
        tmp_path,
        3,
        "amdgpu",
        {
            "temp1_input": "61250",
            "temp1_label": "edge",
            "power1_average": "187500000",
            "power1_input": "200000000",
            "power1_label": "board",
            "fan1_input": "1234",
            "curr1_input": "2500",
            "in1_input": "900",
            "temp2_input": "unavailable",
        },
    )
    chip(tmp_path, 1, "k10temp", {"temp1_input": "50000"})
    orphan = tmp_path / "hwmon2"
    orphan.mkdir()
    (orphan / "temp1_input").write_text("42000\n")
    assert hwmon.chips(tmp_path) == [
        ("k10temp", {"temp1": Reading(50, "°C")}),
        (
            "amdgpu",
            {
                "edge": Reading(61.25, "°C"),
                "board": Reading(200, "W"),
                "board average": Reading(187.5, "W"),
                "fan1": Reading(1234, "rpm"),
                "curr1": Reading(2.5, "A"),
            },
        ),
    ]


@pytest.mark.parametrize(
    ("vendor", "pci_class", "expected"),
    [
        ("0x1002", "0x030000", True),
        ("0x1002", "0x038000", True),
        ("0x10de", "0x030000", False),
        ("0x1002", "0x040300", False),
    ],
)
def test_amdgpu_gives_checks_pci_display_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vendor: str, pci_class: str, expected: bool
) -> None:
    pci = tmp_path / "pci"
    device = pci / "0000:03:00.0"
    device.mkdir(parents=True)
    (pci / "0000:02:00.0").mkdir()  # a device that disappeared while being listed
    (device / "vendor").write_text(vendor + "\n")
    (device / "class").write_text(pci_class + "\n")
    monkeypatch.setattr(amdgpu, "PCI", pci)
    source = Amdgpu(str(tmp_path / "drm"))
    assert source.gives() == (frozenset({"gpu_c", "gpu_w", "gpu_use", "gpu_vram"}) if expected else frozenset())
    assert source.read() == {}  # PCI discovery works before the driver creates a DRM card
