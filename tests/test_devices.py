"""The device list with configured, busy and unsupported fake panels."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial.cli import main
from pixdial.devices import Found, Slv3, usbfs


def test_devices_identifies_configured_names_busy_panels_and_missing_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'sources = []\n[[panels]]\nname = "top panel"\nserial = "TOP"\n'
        '[[panels]]\nserial = "BOTTOM"\n[[panels]]\nserial = "UNPLUGGED"\n'
    )
    found = [
        Found("TOP", "usb 1-2", True, held="pixdial (pid 42)"),
        Found("BOTTOM", "usb 1-3", True, held="another-daemon (pid 99)"),
        Found("EXTRA", "usb 1-4", False, held="a program of another user"),
    ]
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: found))
    assert main(["--config", str(config), "devices"]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == [
        "slv3  TOP  usb 1-2  in use by pixdial (pid 42)  panel 'top panel'",
        "slv3  BOTTOM  usb 1-3  in use by another-daemon (pid 99)  panel '2'",
        "slv3  EXTRA  usb 1-4  no access (`pixdial setup` gives it)  not in the config",
    ]
    assert out.err == ""


def test_devices_with_only_unsupported_screens_still_reports_no_drivable_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text("sources = []\n")
    monkeypatch.setattr(usbfs, "products", lambda vendor: [(0x0028, "1-4")])
    assert main(["--config", str(config), "devices"]) == 1
    out = capsys.readouterr()
    assert "1cbe:0028  usb 1-4" in out.out and "turing-smart-screen-python" in out.out
    assert "no panels attached" in out.err and "USB 2 header" in out.err
