"""Sensor discovery uses a fake hwmon tree and prints source tables that can be read back."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pixdial import config as cfg
from pixdial.cli import main
from pixdial.readings import Reading
from pixdial.sources import Hwmon, hwmon
from tests.test_sources import chip


def test_sensors_lists_values_limits_and_usable_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chip(
        tmp_path,
        0,
        "example",
        {
            "temp1_input": "61500",
            "temp1_label": 'CPU "package"',
            "temp1_max": "90000",
            "temp1_crit": "100000",
            "temp2_input": "42000",
            "temp2_label": 'CPU "package"',
            "temp2_max": "80000",
            "power1_input": "310000000",
            "power1_crit": "1000000000",
            "power2_average": "45000000",
            "fan1_input": "0",
            "fan1_max": "1800",
            "in0_input": "12050",
            "in0_max": "13000",
            "curr1_input": "2500",
            "curr1_crit": "10000",
        },
    )
    chip(tmp_path, 1, "empty", {})
    monkeypatch.setattr(hwmon, "HWMON", tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    # Discovery works even with a missing config; it neither builds sources nor opens devices.
    assert main(["--config", str(tmp_path / "absent.toml"), "sensors"]) == 0
    out, error = capsys.readouterr()
    assert not error
    assert '# example/temp1 (CPU "package"): 61.5 °C; limit 100 °C' in out
    assert '# example/temp2 (CPU "package"): 42 °C; limit 80 °C' in out
    assert "# example/in0: 12.05 V; limit 13 V" in out
    assert "# example/curr1: 2.5 A; limit 10 A" in out
    assert "# example/fan1: 0 rpm; limit 1800 rpm" in out
    assert "# example/power2_average: 45 W; limit not reported" in out
    assert "# empty: no sensors" in out
    config = cfg.parse(tomllib.loads(out), tmp_path / "config.toml")
    assert len(config.sources) == 7
    values = {}
    for _, source in cfg.sources(config):
        assert isinstance(source, Hwmon)
        source.root = tmp_path
        values.update(source.read())
    assert values == {
        "example_temp1": Reading(61.5, "°C", max=100),
        "example_temp2": Reading(42, "°C", max=80),
        "example_power1": Reading(310, "W", max=1000),
        "example_power2_average": Reading(45, "W"),
        "example_fan1": Reading(0, "rpm", max=1800),
        "example_in0": Reading(12.05, "V", max=13),
        "example_curr1": Reading(2.5, "A", max=10),
    }
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_sensors_keeps_unreadable_sensors_and_repeated_chip_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chip(tmp_path, 0, "coretemp", {"temp1_input": "bad", "temp2_input": "50000"})
    chip(tmp_path, 1, "coretemp", {"temp1_input": "60000"})
    (tmp_path / "hwmon0" / "temp3_input").symlink_to(tmp_path / "missing")
    monkeypatch.setattr(hwmon, "HWMON", tmp_path)
    assert main(["sensors"]) == 0
    out = capsys.readouterr().out
    assert "# coretemp/temp1: unavailable" in out
    assert "# coretemp/temp3: unavailable" in out
    assert "# coretemp/temp1: 60 °C" in out
    assert "# coretemp/temp2: 50 °C" in out
    assert len(tomllib.loads(out)["sources"]) == 4


def test_sensors_without_hwmon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hwmon, "HWMON", tmp_path / "missing")
    assert main(["sensors"]) == 1
    assert "no hwmon chips found" in capsys.readouterr().out


@pytest.mark.parametrize("limit_name", ["power1_average_max", "power1_crit", "power1_max"])
def test_hwmon_reads_an_average_with_its_limit(tmp_path: Path, limit_name: str) -> None:
    chip(tmp_path, 0, "amdgpu", {"power1_average": "45000000", limit_name: "90000000"})
    source = Hwmon({"gpu_w": "amdgpu/power1_average"}, root=str(tmp_path))
    assert source.read() == {"gpu_w": Reading(45, "W", max=90)}
