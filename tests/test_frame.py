"""A frame's memory: freed as soon as it is drawn, not at the next cycle collection; the gauge gradients kept."""

from __future__ import annotations

import gc
import tracemalloc
import weakref

from pixdial.designs import BUILTIN, THEMES, geometry
from pixdial.designs.frame import Frame
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
