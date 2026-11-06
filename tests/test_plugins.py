"""Plugins: the example plugin found as local code and as an installed package's entry points."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from pixdial import config as cfg
from pixdial import plugins
from pixdial.designs import BUILTIN, THEMES, Design
from pixdial.readings import Snapshot

EXAMPLE = Path(__file__).parent.parent / "examples" / "plugin"


@pytest.fixture
def example(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.syspath_prepend(str(EXAMPLE))
    yield
    sys.modules.pop("pixdial_example", None)


def test_local_code_by_module_and_class(example: None, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[[panels]]\ndevice = "pixdial_example:Folder"\npath = "frames"\n'
        '[[sources]]\ntype = "pixdial_example:LoadAverage"\n'
    )
    config = cfg.load(path)
    ((_, device),) = cfg.devices(config)
    ((_, source),) = cfg.sources(config)
    assert type(device).__name__ == "Folder" and type(source).__name__ == "LoadAverage"
    assert source.read()["loadavg"].max


def test_entry_points(example: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def entry_points(group: str) -> list[EntryPoint]:
        return {
            "pixdial.designs": [
                EntryPoint("big", "pixdial_example:Big", group),
                EntryPoint("crown", "pixdial_example:Big", group),  # can't replace a built-in
                EntryPoint("broken", "pixdial_example:Nothing", group),
                EntryPoint("wrong", "pixdial_example:LoadAverage", group),  # not a design
            ]
        }.get(group, [])

    monkeypatch.setattr(plugins, "entry_points", entry_points)
    found, broken = plugins.available("designs", Design, BUILTIN)
    assert list(found)[-1] == "big" and found["crown"] is BUILTIN["crown"]
    assert set(broken) == {"crown", "broken", "wrong"}
    big = plugins.resolve("designs", Design, BUILTIN, "big")(THEMES["warm"])
    big.update(Snapshot({}, 0), 0, 0.1)
    assert big.render(0).size == (400, 400)
    with pytest.raises(plugins.PluginError, match="failed to load"):
        plugins.resolve("designs", Design, BUILTIN, "broken")
    with pytest.raises(plugins.PluginError, match="no design 'nope'"):
        plugins.resolve("designs", Design, BUILTIN, "nope")
