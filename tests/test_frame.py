"""A frame's memory: freed as soon as it is drawn, not at the next cycle collection; the gauge gradients kept. Where
a still part shows the background."""

from __future__ import annotations

import gc
import tracemalloc
import weakref

import numpy as np
import pytest

from pixdial.designs import BUILTIN, THEMES, geometry
from pixdial.designs.frame import Frame
from pixdial.gallery import Demo
from pixdial.readings import Reading, Snapshot


def test_a_drawn_frame_is_freed_without_the_cycle_collector() -> None:
    gc.disable()  # the runtime draws up to 30 frames a second; each holds two 400 x 400 colour arrays
    try:
        frame = Frame(geometry.kit(1), THEMES["warm"], None, 0.08)
        frame.disc(200, 200, 40, (255, 150, 50))
        frame.finish()
        gone = weakref.ref(frame)
        del frame
        assert gone() is None
    finally:
        gc.enable()


def test_a_limit_that_keeps_changing_keeps_memory_bounded() -> None:
    gpu = BUILTIN["gpu"](THEMES["warm"])
    geometry.Ring.gradient.cache_clear()
    tracemalloc.start()
    try:
        for watts in range(400, 600):  # a GPU's power limit moving a watt at a time: 200 gauge scales
            gpu.update(Snapshot({"gpu_w": Reading(300.0, "W", max=watts)}, 0.0), 0.0, 0.1)
            gpu.still()
        kept, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert kept < 40e6  # bytes; 130 MB in 0.1.2, which kept every gradient


@pytest.mark.parametrize("state", ["idle", "busy", "missing"])
@pytest.mark.parametrize("name", BUILTIN)
def test_the_still_part_says_where_the_background_shows(name: str, state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drawn over another background, every design's still part is its picture with that background where it shows:
    px + (other - background) * bare, so a backdrop can go under it without drawing it again."""
    design = Demo(BUILTIN[name](THEMES["warm"]), state, {}).design
    kit, theme = design.kit, design.theme
    px, _, bare = design.still()
    assert bare is not None
    other = np.random.default_rng(1).uniform(0, 255, (kit.size, kit.size, 3)).astype(np.float32)
    expected = px + (other - kit.background(theme)) * bare
    monkeypatch.setattr(geometry.Kit, "background", lambda self, theme: other)
    assert np.abs(design.still().px - expected).max() < 0.01
    assert ((bare >= 0) & (bare <= 1)).all()
