"""A frame's memory: freed as soon as it is drawn, not at the next cycle collection."""

from __future__ import annotations

import gc
import weakref

from pixdial.designs import THEMES, geometry
from pixdial.designs.frame import Frame


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
