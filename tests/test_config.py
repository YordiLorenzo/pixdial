"""The config file: what it accepts, and errors that say where the problem is."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial import config as cfg
from pixdial.devices import Png, Slv3
from pixdial.readings import Meta
from pixdial.runtime import Report
from pixdial.sources import Cpu, Hwmon

GOOD = """
theme = "ember"
layout = ["crown", "gpu:ice"]
rotate_every = 30

[[panels]]
name = "top"
serial = "a1b2"
turn = 180

[[panels]]
device = "png"
path = "~/panel.png"

[[sources]]
type = "cpu"

[[sources]]
type = "hwmon"
readings = { cpu_c = "k10temp/Tctl" }

[[sources]]
type = "hwmon"
readings = { psu_c = ["corsairpsu/temp1", "corsairpsu/temp2"] }

[readings.psu_w]
max = 1500

[readings.pins]
max = 9.5
warn = 9.2
label = "12V-2x6"
"""


def load(tmp_path: Path, text: str) -> cfg.Config:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return cfg.load(path)


def error(tmp_path: Path, text: str) -> str:
    with pytest.raises(cfg.ConfigError) as caught:
        config = load(tmp_path, text)
        cfg.devices(config)
        cfg.sources(config)
        cfg.layout(config, cfg.catalog(config))
    return str(caught.value)


def test_a_full_config(tmp_path: Path) -> None:
    config = load(tmp_path, GOOD)
    assert config.theme == "ember"
    assert config.rotate_every == 30
    assert [p.name for p in config.panels] == ["top", "2"]
    devices = cfg.devices(config)
    assert isinstance(devices[0][1], Slv3) and devices[0][1].turn == 180
    assert isinstance(devices[1][1], Png) and devices[1][1].path == Path.home() / "panel.png"
    sources = cfg.sources(config)
    assert [name for name, _ in sources] == ["cpu", "hwmon 1", "hwmon 2"]
    assert isinstance(sources[0][1], Cpu) and isinstance(sources[2][1], Hwmon)
    assert config.readings["pins"] == Meta(9.5, 9.2, "12V-2x6")
    assert cfg.layout(config, cfg.catalog(config)).default == ("crown", "gpu:ice")


def test_defaults(tmp_path: Path) -> None:
    config = load(tmp_path, '[[panels]]\nserial = "a"\n[[panels]]\nserial = "b"\n')
    assert config.sources == cfg.DEFAULT_SOURCES
    assert cfg.layout(config, cfg.catalog(config)).default == ("crown", "gpu")


def test_no_file_at_the_default_place_means_the_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfg.load().panels == ()
    with pytest.raises(cfg.ConfigError, match="no such file"):
        cfg.load(tmp_path / "missing.toml")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("theme = [", "Invalid value"),
        ("colour = 1", "unknown key 'colour'"),
        ("theme = 3", "theme: must be text, not 3"),
        ("rotate_every = 0", "rotate_every: must be above 0"),
        ("rotate_every = true", "rotate_every: must be a number"),
        ('theme = "neon"', "no theme 'neon'"),
        ('layout = ["crown", "nope"]\n[[panels]]\nserial="a"\n[[panels]]\nserial="b"', "layout: no design 'nope'"),
        ('layout = ["crown"]\n[[panels]]\nserial="a"\n[[panels]]\nserial="b"', "layout: 1 designs for 2 panels"),
        ('rotation = ["crown", "nope"]', "rotation: no design 'nope'"),
        ("[[panels]]\nturn = 180", "panels[0]: slv3 needs serial"),
        ('[[panels]]\nserial = "a"\nturn = 45', "panels[0]: turn must be 0, 90, 180 or 270"),
        ('[[panels]]\nserial = "a"\nspin = 1', "panels[0]: slv3 takes no 'spin' (it takes serial, turn, brightness)"),
        ('[[panels]]\ndevice = "lcd9000"', "panels[0]: no device 'lcd9000'"),
        ('[[panels]]\nname = "a"\nserial = "1"\n[[panels]]\nname = "a"\nserial = "2"', "two panels named 'a'"),
        ("[[sources]]\nperiod = 1", "sources[0]: needs type"),
        ('[[sources]]\ntype = "hwmon"\nreadings = { cpu_c = "Tctl" }', "sources[0]: cpu_c: 'Tctl' is not chip/sensor"),
        ('[[sources]]\ntype = "nope:Thing"', "sources[0]: nope:Thing: No module named 'nope'"),
        ('[readings.psu_w]\nmax = "lots"', "readings.psu_w.max: must be a number"),
        ("[readings.psu_w]\nmin = 1", "readings.psu_w: unknown key 'min'"),
    ],
)
def test_errors_say_where(tmp_path: Path, text: str, message: str) -> None:
    assert message in error(tmp_path, text)


def test_run_needs_panels(tmp_path: Path) -> None:
    with pytest.raises(cfg.ConfigError, match="no \\[\\[panels\\]\\]"):
        cfg.runner(load(tmp_path, ""), Report())
