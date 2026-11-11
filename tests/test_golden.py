"""Every design in every theme and demo state against its golden image. UPDATE_GOLDEN=1 writes them anew; a
mismatch leaves the new picture next to the golden one as NAME.actual.png."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFont

from pixdial import demo
from pixdial.designs import BUILTIN, THEMES, geometry
from pixdial.gallery import Demo
from pixdial.readings import Reading
from pixdial.runtime import Feed

GOLDEN = Path(__file__).parent / "golden"
STATES = ("idle", "busy", "full", "missing")


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("name", BUILTIN)
def test_matches_its_golden_image(name: str, theme: str, state: str) -> None:
    image = Demo(BUILTIN[name](THEMES[theme]), state, {}).render()
    path = GOLDEN / f"{name}-{theme}-{state}.png"
    if os.environ.get("UPDATE_GOLDEN"):
        image.save(path, optimize=True)
        return
    expected = np.asarray(Image.open(path).convert("RGB"), np.int16)
    diff = np.abs(np.asarray(image, np.int16) - expected).max(axis=-1)
    # Another FreeType may set a few text edges apart; a change of colour or place moves far more pixels than 0.2 %
    if (diff > 1).mean() > 0.002:
        image.save(path.with_suffix(".actual.png"))
        pytest.fail(f"{path.name}: {np.count_nonzero(diff > 1)} pixels differ (by up to {diff.max()})")


@pytest.fixture
def no_raqm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pillow as a clean install without libraqm (or its FriBiDi) has it: the basic text layout, with fresh fonts."""
    monkeypatch.setattr(ImageFont.core, "HAVE_RAQM", False)
    geometry.kit.cache_clear()
    yield
    geometry.kit.cache_clear()  # the next test's fonts use raqm again


@pytest.mark.parametrize("name", BUILTIN)
def test_draws_without_raqm(name: str, no_raqm: None) -> None:
    assert geometry.kit(1).font("Bold", 30).layout_engine == ImageFont.Layout.BASIC
    Demo(BUILTIN[name](THEMES["warm"]), "busy", {}).render()


class Recorded(dict[str, Reading]):
    """Readings that note each key a design looks up."""

    def __init__(self, readings: dict[str, Reading], seen: set[str]) -> None:
        super().__init__(readings)
        self.seen = seen

    def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
        self.seen.add(key)
        return super().get(key, default)


@pytest.mark.parametrize("name", BUILTIN)
def test_a_design_lists_the_readings_it_reads(name: str) -> None:
    cls, seen = BUILTIN[name], set[str]()
    design, feed = cls(THEMES["warm"]), Feed({}, cls.trails)
    for state in ("busy", "waiting"):
        for t in (0.0, 0.5, 1.0):
            design.update(feed.snapshot(Recorded(demo.readings(state, t), seen), t, demo.START + t), t, 0.5)
            design.render(t)
    assert seen == set(cls.reads)
    assert set(cls.needs) <= set(cls.reads)
