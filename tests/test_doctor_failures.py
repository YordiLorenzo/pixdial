"""Doctor failures using fixture configs, fake plugins and fake sources."""

from __future__ import annotations

import functools
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import Mock

import pytest

from pixdial import config as cfg
from pixdial import doctor, plugins
from pixdial.cli import main
from pixdial.devices import Found, Slv3, slv3
from pixdial.readings import Reading
from pixdial.sources import Source


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(doctor, "checks", functools.partial(doctor.checks, wait=lambda seconds: None))
    path = tmp_path / "config.toml"
    path.write_text(f'sources = []\n[[panels]]\ndevice = "png"\npath = "{tmp_path / "panel.png"}"\n')
    return path


def test_doctor_stops_after_an_invalid_config(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config.write_text("theme = [\n")
    monkeypatch.setattr(cfg, "sources", lambda config: pytest.fail("built sources for an invalid config"))
    assert main(["--config", str(config), "doctor"]) == 1
    out = capsys.readouterr()
    assert "FAIL  config" in out.out and str(config) in out.out
    assert "Invalid value" in out.out and "source " not in out.out
    assert out.err == ""


def test_doctor_reports_missing_fonts(
    config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "Lato-Regular.ttf").write_bytes(b"")
    monkeypatch.setattr(doctor, "FONTS", fonts)
    assert main(["--config", str(config), "doctor"]) == 1
    assert "FAIL  fonts            missing Lato Black, Bold" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["designs", "sources", "devices"])
def test_doctor_reports_a_broken_plugin_and_continues_the_checks(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    def entries(group: str) -> list[EntryPoint]:
        return (
            [EntryPoint("broken", "pixdial_missing_test_plugin:Missing", group)] if group == f"pixdial.{kind}" else []
        )

    monkeypatch.setattr(plugins, "entry_points", entries)
    assert main(["--config", str(config), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  plugin broken" in out and "No module named 'pixdial_missing_test_plugin'" in out
    assert "ok    panel 1" in out and "ok    layout" in out


@pytest.mark.parametrize(
    ("text", "check", "reason"),
    [
        ('sources = []\n[[panels]]\ndevice = "missing"\n', "panels", "no device 'missing'"),
        ('[[sources]]\ntype = "hwmon"\nreadings = {cpu_c = "bad"}\n', "sources", "not chip/sensor"),
        ('sources = []\ntheme = "missing"\n', "layout", "no theme 'missing'"),
    ],
)
def test_doctor_reports_errors_when_building_the_config(
    config: Path, capsys: pytest.CaptureFixture[str], text: str, check: str, reason: str
) -> None:
    config.write_text(text)
    assert main(["--config", str(config), "doctor"]) == 1
    out = capsys.readouterr()
    assert f"FAIL  {check}" in out.out and reason in out.out
    assert out.err == ""


@pytest.mark.parametrize("attached", [False, True])
def test_doctor_reports_a_missing_panel_or_missing_access(
    config: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], attached: bool
) -> None:
    config.write_text('sources = []\n[[panels]]\nname = "top panel"\nserial = "SERIAL"\n')
    found = [Found("SERIAL", "usb 1-2", False)] if attached else []
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: found))
    monkeypatch.setattr(slv3, "connect", lambda serial: pytest.fail("doctor opened a panel"))
    assert main(["--config", str(config), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  panel top panel" in out
    assert ("pixdial setup" if attached else "USB 2 header") in out


def test_doctor_reports_a_stale_saved_layout(config: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = cfg.state_path()
    state.parent.mkdir(parents=True)
    state.write_text("removed\n")
    assert main(["--config", str(config), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  layout" in out and "no design 'removed'" in out
    assert state.read_text() == "removed\n"


class Sampled(Source):
    def __init__(self, fail_first: bool, fail_second: bool) -> None:
        self.failures = (fail_first, fail_second)
        self.calls = 0
        self.closed = 0

    def read(self) -> dict[str, Reading]:
        fail = self.failures[self.calls]
        self.calls += 1
        if fail:
            raise OSError("sensor unavailable")
        return {"cpu_c": Reading(61, "°C")}

    def close(self) -> None:
        self.closed += 1


@pytest.mark.parametrize("fail_first", [False, True])
@pytest.mark.parametrize("fail_second", [False, True])
def test_doctor_samples_twice_and_closes_failed_and_working_sources(
    tmp_path: Path, fail_first: bool, fail_second: bool
) -> None:
    source = Sampled(fail_first, fail_second)
    healthy = Sampled(False, False)
    waits: list[float] = []
    config = cfg.Config(tmp_path / "config.toml", sources=())
    result = list(doctor.sources(config, [("sensor", source), ("healthy", healthy)], waits.append))
    assert len(result) == 2
    assert result[0].status == (doctor.FAIL if fail_second else doctor.OK)
    assert result[0].detail == ("sensor unavailable" if fail_second else "cpu_c 61 °C")
    assert result[0].readings == ({} if fail_second else {"cpu_c": Reading(61, "°C")})
    assert result[1].status == doctor.OK
    assert source.calls == healthy.calls == 2
    assert source.closed == healthy.closed == 1
    assert waits == [1.0]


def test_firmware_reports_an_open_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = Mock(side_effect=OSError("panel unplugged"))
    monkeypatch.setattr(slv3, "connect", connect)
    assert doctor.firmware(Found("SERIAL", "usb 1-2", True)) == "could not open it: panel unplugged"
    connect.assert_called_once_with("SERIAL")


def test_firmware_closes_the_panel_even_if_turning_it_off_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = Mock(return_value="firmware test-version")
    off = Mock(side_effect=OSError("panel unplugged"))
    closed = Mock()
    monkeypatch.setattr(Slv3, "open", opened)
    monkeypatch.setattr(Slv3, "off", off)
    monkeypatch.setattr(Slv3, "close", closed)
    assert doctor.firmware(Found("SERIAL", "usb 1-2", True)) == "firmware test-version"
    opened.assert_called_once_with()
    off.assert_called_once_with()
    closed.assert_called_once_with()
