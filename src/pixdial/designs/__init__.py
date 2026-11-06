"""Designs: pure renders from a snapshot of readings to a 400 x 400 picture, with no I/O.

What a design needs to draw is importable from here; see the README's "Writing a design".
"""

from ..readings import Snapshot, TrailSpec
from .agents import Quota
from .base import DEFAULT_MAX, Design, fmt, joined, limit, rnd
from .clock import Clock
from .colour import LOAD, THEMES, Scale, Theme, current, lerp, share, solid, temperature
from .cpu import Crown, Grid, Minimal, Orb, Radar
from .frame import DASH, Frame, Pixels, Still, add, disc, glow_disc, paint, with_text
from .geometry import MID, SIZE, Kit, Ring, on_circle
from .gpu import Gpu, Pins, Twin
from .motion import Eased
from .power import Flow, History, Psu
from .thermals import Thermals

BUILTIN: dict[str, type[Design]] = {
    d.name: d for d in (Crown, Gpu, Psu, Pins, Flow, Quota, History, Twin, Clock, Minimal, Thermals, Orb, Radar, Grid)
}

__all__ = [
    "BUILTIN",
    "DASH",
    "DEFAULT_MAX",
    "LOAD",
    "MID",
    "SIZE",
    "THEMES",
    "Design",
    "Eased",
    "Frame",
    "Kit",
    "Pixels",
    "Ring",
    "Scale",
    "Snapshot",
    "Still",
    "Theme",
    "TrailSpec",
    "add",
    "current",
    "disc",
    "fmt",
    "glow_disc",
    "joined",
    "lerp",
    "limit",
    "on_circle",
    "paint",
    "rnd",
    "share",
    "solid",
    "temperature",
    "with_text",
]
