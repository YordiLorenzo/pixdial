"""Which design each panel shows: named in a layout (name or name:theme per panel), or every design in turn."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..designs import Design, Theme

ROTATE = "rotate"


class Catalog:
    """The designs and themes a layout can name; a design named without a theme gets the default one."""

    def __init__(self, designs: Mapping[str, type[Design]], themes: Mapping[str, Theme], theme: str) -> None:
        self.designs, self.themes, self.theme = designs, themes, theme

    def check(self, spec: str) -> None:
        name, _, theme = spec.partition(":")
        if name not in self.designs:
            raise ValueError(f"no design {name!r} (designs: {', '.join(self.designs)})")
        if theme and theme not in self.themes:
            raise ValueError(f"no theme {theme!r} (themes: {', '.join(self.themes)})")

    def make(self, spec: str, scale: int = 1) -> Design:
        self.check(spec)
        name, _, theme = spec.partition(":")
        return self.designs[name](self.themes[theme or self.theme], scale)


class Layout:
    """The layout file (written by `show`, followed by `run`), the config's default where there is none, and the
    rotation: under "rotate" each panel steps through the rotation every `every` seconds, all on the same beat, as
    far apart in the list as the panels allow, so no two show the same design."""

    def __init__(
        self,
        catalog: Catalog,
        panels: int,
        path: Path,
        default: Sequence[str],
        rotation: Sequence[str],
        every: float,
    ) -> None:
        self.catalog, self.panels, self.path = catalog, panels, path
        self.default = self.check(default)
        self.rotation, self.every = list(rotation), every

    def check(self, specs: Sequence[str]) -> tuple[str, ...]:
        """The specs, or ValueError naming what is wrong with them."""
        if list(specs) == [ROTATE]:
            return (ROTATE,)
        for spec in specs:
            self.catalog.check(spec)
        if len(specs) != self.panels:
            raise ValueError(f"{len(specs)} designs for {self.panels} panels")
        return tuple(specs)

    def load(self) -> tuple[str, ...]:
        try:
            return self.check(self.path.read_text().split())
        except FileNotFoundError:
            return self.default

    def save(self, specs: Sequence[str]) -> None:
        specs = self.check(specs)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_name(self.path.name + ".part")
        part.write_text(" ".join(specs) + "\n")
        part.replace(self.path)  # whole, so `run` never reads half a line

    def stamp(self) -> float | None:
        """What changes when the file does."""
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None

    def showing(self, specs: tuple[str, ...], wall: float) -> tuple[str, ...]:
        """The designs to show at wall-clock time wall."""
        if specs != (ROTATE,):
            return specs
        names, step = self.rotation, int(wall // self.every)
        return tuple(names[(step + i * len(names) // self.panels) % len(names)] for i in range(self.panels))
