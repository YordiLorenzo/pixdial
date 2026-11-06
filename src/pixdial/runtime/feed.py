"""Snapshots for the designs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..readings import Meta, Reading, Snapshot, Trail, TrailSpec


class Feed:
    """Turns fresh readings into a snapshot: with the config's meta, the trails the designs keep (each fed every
    snapshot, so a design has its past when it comes on), and the wall-clock time."""

    def __init__(self, meta: Mapping[str, Meta], trails: Iterable[TrailSpec]) -> None:
        self.meta = meta
        self.trails = {spec: Trail(spec) for spec in trails}

    def snapshot(self, readings: Mapping[str, Reading], now: float, wall: float) -> Snapshot:
        snapshot = Snapshot(readings, wall, self.meta, self.trails)
        for spec, trail in self.trails.items():
            trail.add(snapshot.number(spec.key), now)
        return snapshot
