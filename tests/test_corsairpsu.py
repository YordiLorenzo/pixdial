"""The default Corsair source, including machines without a PSU sensor."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial import config as cfg
from pixdial.readings import Reading
from pixdial.runtime import Report, Sampler
from pixdial.sources import Source, hwmon
from tests import logged
from tests.test_sources import chip

PSU = {
    "power1_input": "312000000",
    "temp1_input": "41000",
    "temp1_crit": "70000",
    "temp2_input": "44500",
    "temp2_crit": "75000",
    "fan1_input": "0",
}


def source(root: Path) -> Source:
    config = cfg.parse({"sources": [{"type": "corsairpsu", "root": str(root)}]}, root / "config.toml")
    return cfg.sources(config)[0][1]


def test_corsair_readings_are_in_the_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chip(tmp_path, 4, "corsairpsu", PSU)
    monkeypatch.setattr(hwmon, "HWMON", tmp_path)
    config = cfg.parse({}, tmp_path / "config.toml")
    built = dict(cfg.sources(config))
    assert "corsairpsu" in built
    psu = built["corsairpsu"]
    assert psu.gives() == frozenset({"psu_w", "psu_c", "psu_fan"})
    assert psu.read() == {
        "psu_w": Reading(312, "W"),
        "psu_c": Reading(44.5, "°C", max=70),
        "psu_fan": Reading(0, "rpm"),
    }


@pytest.mark.parametrize("present", [False, True])
def test_default_layout_and_rotation_follow_corsair_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: bool
) -> None:
    monkeypatch.setattr("pixdial.sources.amdgpu.PCI", tmp_path / "pci")
    monkeypatch.setattr("pixdial.sources.nvml.LIBRARY", "libnvidia-ml-not-here.so.1")
    if present:
        chip(tmp_path, 4, "corsairpsu", PSU)
    monkeypatch.setattr(hwmon, "HWMON", tmp_path)
    config = cfg.parse({"panels": [{"serial": str(i)} for i in range(14)]}, tmp_path / "config.toml")
    assert any(e.kind == "corsairpsu" for e in config.sources)
    layout = cfg.layout(config, cfg.catalog(config))
    for name in ("psu", "flow", "history"):
        assert (name in layout.default) is present
        assert (name in layout.rotation) is present


def test_corsair_is_silent_without_its_chip(tmp_path: Path) -> None:
    chip(tmp_path, 0, "otherpsu", PSU)
    lines: list[str] = []
    psu = source(tmp_path)
    assert psu.gives() == frozenset()
    assert psu.read() == {}
    sampler = Sampler([("corsairpsu", psu)], Report(logged(lines)), clock=lambda: 0.0)
    sampler.sample(0)
    sampler.sample(0)
    assert lines == [] and sampler.fresh(0) == {}


def test_corsair_finds_late_chips_and_drops_cached_paths(tmp_path: Path) -> None:
    psu = source(tmp_path)
    assert psu.read() == {}
    chip(tmp_path, 0, "corsairpsu", PSU)
    assert psu.read()["psu_w"].value == 312
    (tmp_path / "hwmon0").rename(tmp_path / "unplugged")
    assert psu.read() == {} and psu.gives() == frozenset()
    chip(tmp_path, 0, "otherpsu", {**PSU, "power1_input": "999000000"})
    chip(tmp_path, 2, "corsairpsu", {**PSU, "power1_input": "250000000"})
    assert psu.read()["psu_w"].value == 250
    (tmp_path / "hwmon2").rename(tmp_path / "hwmon3")
    assert psu.read()["psu_w"].value == 250


def test_corsair_only_gives_present_sensors(tmp_path: Path) -> None:
    chip(tmp_path, 0, "corsairpsu", {"temp1_input": "41000", "temp1_crit": "70000"})
    psu = source(tmp_path)
    assert psu.gives() == frozenset({"psu_c"})
    assert psu.read() == {"psu_c": Reading(41, "°C", max=70)}
    config = cfg.Config(tmp_path / "config.toml")
    assert "psu" in cfg.skipped(cfg.catalog(config), [("corsairpsu", psu)])


def test_corsair_skips_chips_that_disappear_during_discovery(tmp_path: Path) -> None:
    (tmp_path / "hwmon0").mkdir()  # the name file disappeared with the device
    chip(tmp_path, 1, "corsairpsu", PSU)
    assert source(tmp_path).read()["psu_w"].value == 312
