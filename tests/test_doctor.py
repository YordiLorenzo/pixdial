"""`doctor`, `doctor --share` and `devices`: what they say about panels, sources and the machine, and what they keep
out of a report."""

from __future__ import annotations

import functools
import platform
import socket
import sys
from pathlib import Path

import pytest

from pixdial import __version__, doctor
from pixdial.cli import main
from pixdial.devices import Found, Slv3, slv3, usbfs
from pixdial.sources import hwmon, nvml

A, B = "SERIALAAA111", "SERIALBBB222"
WHERE = "usb 1-2 (/dev/bus/usb/001/005)"
CHIPS, PRODUCTS = hwmon.chips, usbfs.products  # the real ones, which the fixture below replaces


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty home: no config, no state, no NVIDIA library, no hwmon chips, nothing else on USB."""
    home = tmp_path / "home"
    home.mkdir()
    for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(nvml, "LIBRARY", "libnvidia-ml-not-here.so.1")
    monkeypatch.setattr(hwmon, "chips", lambda: CHIPS(tmp_path / "no-hwmon"))
    monkeypatch.setattr(usbfs, "products", lambda vendor: [])
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: []))
    monkeypatch.setattr(doctor, "checks", functools.partial(doctor.checks, wait=lambda s: None))
    return home


def attach(monkeypatch: pytest.MonkeyPatch, *found: Found) -> None:
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: list(found)))


def config(home: Path, text: str) -> Path:
    path = home / ".config" / "pixdial" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def doctor_out(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    status = main(["doctor", *args])
    return status, capsys.readouterr().out


# ------------------------------------------------------------------ usbfs: who has a device, what else is attached


def device_dir(sysfs: Path, port: str, product: str, vendor: str = "1cbe", driver: str | None = None) -> None:
    d = sysfs / port
    d.mkdir(parents=True)
    for name, text in (("idVendor", vendor), ("idProduct", product), ("busnum", "1"), ("devnum", "5")):
        (d / name).write_text(text + "\n")
    (d / "serial").write_text(A + "\n")
    if driver:
        (sysfs / f"{port}:1.0").mkdir()
        (sysfs / f"{port}:1.0" / "driver").symlink_to(f"../../../bus/usb/drivers/{driver}")


def test_a_claimed_device_names_the_program_that_has_it(tmp_path: Path) -> None:
    sysfs, proc = tmp_path / "sys", tmp_path / "proc"
    device_dir(sysfs, "1-2", "0005", driver="usbfs")
    device_dir(sysfs, "1-3", "0005")
    (proc / "42" / "fd").mkdir(parents=True)
    (proc / "42" / "comm").write_text("pixdial\n")
    (proc / "42" / "fd" / "7").symlink_to("/dev/bus/usb/001/005")
    (proc / "77" / "fd").mkdir(parents=True)  # a process with other files open
    (proc / "77" / "comm").write_text("bash\n")
    (proc / "77" / "fd" / "0").symlink_to("/dev/pts/0")
    held = usbfs.UsbDevice(A, "/dev/bus/usb/001/005", "1-2")
    assert usbfs.holder(held, sysfs, proc) == "pixdial (pid 42)"
    assert usbfs.holder(usbfs.UsbDevice(A, "/dev/bus/usb/001/005", "1-3"), sysfs, proc) == ""
    (proc / "42" / "fd" / "7").unlink()  # the program that has it runs as another user: its fds can't be read
    assert usbfs.holder(held, sysfs, proc) == "a program of another user"


def test_every_device_of_a_vendor_is_listed(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    device_dir(sysfs, "1-2", "0005")
    device_dir(sysfs, "1-4", "0028")
    device_dir(sysfs, "1-5", "c52b", vendor="046d")
    (sysfs / "usb1").mkdir()  # a hub without the files
    assert PRODUCTS(0x1CBE, sysfs) == [(0x0005, "1-2"), (0x0028, "1-4")]


# ------------------------------------------------------------------ doctor


def test_with_no_config_it_lists_the_panels_and_prints_a_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch, Found(A, WHERE, True), Found(B, "usb 1-3 (/dev/bus/usb/001/006)", True))
    status, out = doctor_out(capsys)
    assert status == 0
    assert "FAIL" not in out
    assert "skip  panels           none in the config yet; 2 attached" in out
    assert f'      [[panels]]\n      serial = "{A}"\n\n      [[panels]]\n      serial = "{B}"\n' in out
    assert "pixdial setup" in out


def test_with_no_config_and_no_panel_it_names_the_cable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch)
    status, out = doctor_out(capsys)
    assert status == 1
    assert "FAIL  panels           none in the config, and none attached" in out
    assert "USB 2 header" in out and "lsusb | grep 1cbe" in out


def test_a_missing_default_source_is_skipped_with_a_hint(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config(home, f'[[panels]]\ndevice = "png"\npath = "{tmp_path / "p.png"}"\n')
    status, out = doctor_out(capsys)
    assert status == 0, out
    assert "FAIL" not in out
    assert "skip  source nvml      " in out
    assert "      No NVIDIA driver" in out


def test_a_source_the_config_names_fails(home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config(home, f'[[panels]]\ndevice = "png"\npath = "{tmp_path / "p.png"}"\n[[sources]]\ntype = "nvml"\n')
    status, out = doctor_out(capsys)
    assert status == 1
    assert "FAIL  source nvml" in out


def test_a_panel_another_program_holds_fails_with_the_way_out(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config(home, f'[[panels]]\nserial = "{A}"\n[[panels]]\nserial = "{B}"\n')
    held = Found(A, WHERE, True, held="lianli-daemon (pid 9)"), Found(B, WHERE, True, held="pixdial (pid 42)")
    attach(monkeypatch, *held)
    status, out = doctor_out(capsys)
    assert status == 1
    assert "FAIL  panel 1          claimed by lianli-daemon (pid 9)" in out
    assert "lian-li-linux" in out
    assert "ok    panel 2          " in out  # pixdial run has it: that is no problem


def test_doctor_gives_the_version_and_the_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    for prefix, command in (
        ("/home/u/.local/share/uv/tools/pixdial", "uv tool upgrade pixdial"),
        ("/home/u/.local/share/pipx/venvs/pixdial", "pipx upgrade pixdial"),
        ("/home/u/src/pixdial/.venv", "pip install --upgrade pixdial"),
        ("/nix/store/abc-python3-3.13.9", "Nix"),
        ("/usr", "yay -Syu"),
    ):
        monkeypatch.setattr(sys, "prefix", prefix)
        assert command in doctor.upgrade()


# ------------------------------------------------------------------ devices


def test_devices_point_other_screens_to_the_tools_that_drive_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch, Found(A, WHERE, False))
    monkeypatch.setattr(usbfs, "products", lambda vendor: [(0x0005, "1-2"), (0x0007, "1-5"), (0x0028, "1-6")])
    assert main(["devices"]) == 0
    out = capsys.readouterr().out
    assert f"slv3  {A}  {WHERE}  no access (`pixdial setup` gives it)  not in the config" in out
    assert "1cbe:0007  usb 1-5  " in out and "lian-li-linux" in out
    assert "1cbe:0028  usb 1-6  " in out and "turing-smart-screen-python" in out
    assert "1cbe:0005" not in out


def test_devices_without_a_panel_name_the_cable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch)
    assert main(["devices"]) == 1
    assert "USB 2 header" in capsys.readouterr().err


# ------------------------------------------------------------------ doctor --share


def test_share_is_markdown_without_serials_hostname_or_home(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "stat").write_text("cpu 100 0 100 800 0 0 0 0\ncpu0 100 0 100 800 0 0 0 0\n")
    cpu = f'[[sources]]\ntype = "cpu"\nstat = "{tmp_path / "stat"}"\n'
    sources = f'{cpu}[[sources]]\ntype = "command"\nrun = ["sensors-myrig"]\n'
    config(home, f'[[panels]]\nserial = "{A}"\n[[panels]]\nserial = "{B}"\n{sources}')
    b = Found(B, "usb 1-3 (/dev/bus/usb/001/006)", True, held="pixdial (pid 42)")
    attach(monkeypatch, Found(A, WHERE, True), b)
    monkeypatch.setattr(usbfs, "products", lambda vendor: [(0x0005, "1-2"), (0x0005, "1-3"), (0x0007, "1-5")])
    opened: list[str] = []

    def connect(serial: str) -> FirmwareOnly:
        opened.append(serial)
        return FirmwareOnly()

    monkeypatch.setattr(slv3, "connect", connect)
    monkeypatch.setattr(socket, "gethostname", lambda: "myrig")
    chip = tmp_path / "hwmon" / "hwmon0"
    chip.mkdir(parents=True)
    for name, text in (("name", "k10temp"), ("temp1_input", "45250"), ("temp1_label", "Tctl"), ("in0_input", "900")):
        (chip / name).write_text(text + "\n")
    monkeypatch.setattr(hwmon, "chips", lambda: CHIPS(tmp_path / "hwmon"))
    monkeypatch.setattr(platform, "freedesktop_os_release", lambda: {"NAME": "Arch", "PRETTY_NAME": "Arch Linux"})

    status, out = doctor_out(capsys, "--share")
    assert status == 0
    for private in (A, B, str(home), "myrig"):
        assert private not in out
    assert out.startswith("### pixdial doctor --share\n")
    assert f"- pixdial {__version__}, Python {sys.version.split()[0]}, Pillow " in out
    assert "raqm yes" in out
    assert "- Arch Linux, kernel " in out
    assert "- 1cbe:0005 at usb 1-2\n- 1cbe:0005 at usb 1-3\n- 1cbe:0007 at usb 1-5: not a panel pixdial drives" in out
    assert f"- panel-1 at {WHERE}: firmware slv3_2024091003_01" in out
    assert "- panel-2 at usb 1-3 (/dev/bus/usb/001/006): in use by pixdial (pid 42)" in out
    assert opened == [A]  # the free panel, for its firmware; the one pixdial runs on stays as it is
    assert "panel 1" in out and "~/.config/pixdial/config.toml" in out and "sensors-host" in out
    assert "- k10temp: Tctl 45.2 °C\n" in out  # temperatures, power, fans and currents, not voltages
    assert "- crown: cpu_c, cpu_w\n" in out  # the readings each design misses (cpu gives load and threads)


class FirmwareOnly:
    """A panel that answers every command with a version."""

    def write(self, data: bytearray, timeout_ms: int = 1000) -> None:
        pass

    def read(self, timeout_ms: int = 1000) -> bytes:
        return bytes(8) + b"slv3_2024091003_01\0"

    def close(self) -> None:
        pass


def test_share_reads_the_firmware_only_of_a_free_panel_it_may_open(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch, Found(A, WHERE, False), Found(B, WHERE, True, held="a program of another user"))
    monkeypatch.setattr(usbfs, "products", lambda vendor: [(0x0005, "1-2"), (0x0005, "1-3")])
    monkeypatch.setattr(slv3, "connect", lambda serial: pytest.fail("opened a panel"))
    _, out = doctor_out(capsys, "--share")
    assert f"- panel-1 at {WHERE}: no access" in out
    assert f"- panel-2 at {WHERE}: in use by a program of another user" in out


def test_the_snippet_in_a_share_has_no_serials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attach(monkeypatch, Found(A, WHERE, True))
    monkeypatch.setattr(slv3, "connect", lambda serial: FirmwareOnly())
    _, out = doctor_out(capsys, "--share")
    assert A not in out and 'serial = "panel-1"' in out


def test_share_runs_on_this_machine(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor", "--share"]) == 0
    assert platform.release() in capsys.readouterr().out
