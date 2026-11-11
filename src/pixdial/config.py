"""The config file (TOML, under XDG_CONFIG_HOME), checked with errors that say where, and what it builds.

A ConfigError's message says where in the file; the caller adds which file.
"""

from __future__ import annotations

import inspect
import itertools
import json
import os
import tomllib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import NAME, plugins
from .designs import BUILTIN as DESIGNS
from .designs import THEMES, Design
from .devices import BUILTIN as DEVICES
from .devices import Device
from .readings import Meta
from .runtime import Catalog, Feed, Layout, Report, Runner, Sampler, Screen
from .sources import BUILTIN as SOURCES
from .sources import Source


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    """A [[panels]] or [[sources]] table: its kind (a device or source name, or "module:Class") and the rest of its
    keys, which go to that class as options."""

    kind: str
    options: Mapping[str, Any]
    name: str  # in log lines: the panel's name, or the source's kind (numbered when it comes twice)


DEFAULT_SOURCES = (
    Entry("cpu", {}, "cpu"),
    Entry("rapl", {}, "rapl"),
    Entry("amdgpu", {}, "amdgpu"),  # before nvml, so an NVIDIA card's readings win over a Ryzen's built-in GPU
    Entry("nvml", {}, "nvml"),
    Entry("hwmon", {"readings": {"cpu_c": ["k10temp/Tctl", "coretemp/Package id 0"]}}, "hwmon"),
)


@dataclass(frozen=True)
class Config:
    path: Path
    theme: str = "warm"
    layout: tuple[str, ...] = ()  # the designs top to bottom, or ("rotate",); empty: the first designs
    rotate_every: float = 60.0
    rotation: tuple[str, ...] = ()  # empty: every design
    panels: tuple[Entry, ...] = ()
    sources: tuple[Entry, ...] = DEFAULT_SOURCES
    readings: Mapping[str, Meta] = field(default_factory=dict)


def config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / NAME / "config.toml"


def state_path() -> Path:
    """Where `show` keeps the layout for `run`."""
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / NAME / "layout"


def load(path: Path | None = None) -> Config:
    """The config at path, or at the default place; the defaults where there is no file at the default place."""
    file = path or config_path()
    try:
        data = tomllib.loads(file.read_text())
    except FileNotFoundError:
        if path is not None:
            raise ConfigError("no such file") from None
        data = {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(str(error)) from error
    return parse(data, file)


def parse(data: Mapping[str, Any], path: Path) -> Config:
    known(data, "", "theme", "layout", "rotate_every", "rotation", "panels", "sources", "readings")
    layout = get(data, "layout", (str, list), [])
    every = get(data, "rotate_every", (int, float), 60.0)
    if every <= 0:
        raise ConfigError(f"rotate_every: must be above 0, not {every}")
    panels = [panel(table, i) for i, table in enumerate(get(data, "panels", list, []))]
    if dupes := [n for n, count in Counter(p.name for p in panels).items() if count > 1]:
        raise ConfigError(f"panels: two panels named {dupes[0]!r}")
    sources = [entry(table, f"sources[{i}]", "type") for i, table in enumerate(get(data, "sources", list, []))]
    return Config(
        path=path,
        theme=get(data, "theme", str, "warm"),
        layout=tuple(strings([layout] if isinstance(layout, str) else layout, "layout")),
        rotate_every=float(every),
        rotation=tuple(strings(get(data, "rotation", list, []), "rotation")),
        panels=tuple(panels),
        sources=tuple(numbered(sources)) if "sources" in data else DEFAULT_SOURCES,
        readings={key: meta(table, f"readings.{key}") for key, table in get(data, "readings", dict, {}).items()},
    )


def panel(table: Any, i: int) -> Entry:
    """A panel: its device (slv3 unless it says), its name (its number unless it says), the device's options."""
    where = f"panels[{i}]"
    e = entry(table, where, "device", "slv3")
    name = get(e.options, "name", str, str(i + 1), where)
    return Entry(e.kind, {k: v for k, v in e.options.items() if k != "name"}, name)


def entry(table: Any, where: str, kind_key: str, default: str | None = None) -> Entry:
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: must be a table")
    kind = get(table, kind_key, str, default, where)
    if kind is None:
        raise ConfigError(f"{where}: needs {kind_key}")
    return Entry(kind, {k: v for k, v in table.items() if k != kind_key}, kind)


def numbered(entries: Sequence[Entry]) -> list[Entry]:
    """Sources named by their kind, numbered where a kind comes more than once."""
    counts = Counter(e.kind for e in entries)
    seen: Counter[str] = Counter()
    out = []
    for e in entries:
        seen[e.kind] += 1
        out.append(Entry(e.kind, e.options, f"{e.kind} {seen[e.kind]}" if counts[e.kind] > 1 else e.kind))
    return out


def meta(table: Any, where: str) -> Meta:
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: must be a table")
    known(table, where, "max", "warn", "label")
    return Meta(
        max=get(table, "max", (int, float), None, where),
        warn=get(table, "warn", (int, float), None, where),
        label=get(table, "label", str, None, where),
    )


def known(table: Mapping[str, Any], where: str, *keys: str) -> None:
    for key in table:
        if key not in keys:
            raise ConfigError(f"{where + ': ' if where else ''}unknown key {key!r} (known: {', '.join(keys)})")


KINDS = {str: "text", int: "a number", float: "a number", list: "a list", dict: "a table"}


def get(table: Mapping[str, Any], key: str, kind: type | tuple[type, ...], default: Any, where: str = "") -> Any:
    """table[key] if it is of that kind (TOML's true and false are not numbers), else default if it is missing."""
    value = table.get(key, default)
    if value is not default and (not isinstance(value, kind) or isinstance(value, bool)):
        kinds = kind if isinstance(kind, tuple) else (kind,)
        wanted = " or ".join(dict.fromkeys(KINDS[k] for k in kinds))
        raise ConfigError(f"{where + '.' if where else ''}{key}: must be {wanted}, not {value!r}")
    return value


def strings(values: list[Any], where: str) -> list[str]:
    if not all(isinstance(v, str) for v in values):
        raise ConfigError(f"{where}: must be a list of names")
    return values


# ---------------------------------------------------------------- what it builds


def catalog(config: Config) -> Catalog:
    if config.theme not in THEMES:
        raise ConfigError(f"theme: no theme {config.theme!r} (themes: {', '.join(THEMES)})")
    designs, _ = plugins.available("designs", Design, DESIGNS)
    return Catalog(designs, THEMES, config.theme)


def layout(config: Config, catalog: Catalog, built: Sequence[tuple[str, Source]] | None = None) -> Layout:
    """The layout; built: the config's sources, where they are built already (a plugin's may hold a device)."""
    names = list(catalog.designs)
    if not (config.rotation and config.layout):
        if built is None:  # built here only to ask what they give: closed, as a plugin's may hold a device
            temporary = sources(config)
            try:
                left_out = skipped(catalog, temporary)
            finally:
                for _, source in temporary:
                    source.close()
        else:
            left_out = skipped(catalog, built)
        names = [name for name in names if name not in left_out]
    rotation = config.rotation or tuple(names)
    for name in rotation:
        if name not in catalog.designs:
            raise ConfigError(f"rotation: no design {name!r}")
    default = config.layout or tuple(itertools.islice(itertools.cycle(names), len(config.panels)))
    try:
        return Layout(catalog, len(config.panels), state_path(), default, rotation, config.rotate_every)
    except ValueError as error:
        raise ConfigError(f"layout: {error}") from None


def skipped(catalog: Catalog, built: Sequence[tuple[str, Source]]) -> dict[str, list[str]]:
    """The designs the default rotation and layout leave out, each with what it needs that no source gives."""
    given: set[str] = set()
    for _, source in built:
        keys = source.gives()
        if keys is None:  # it may give any reading
            return {}
        given |= keys
    found = {name: [key for key in cls.needs if key not in given] for name, cls in catalog.designs.items()}
    return {name: missing for name, missing in found.items() if missing}


def written(config: Config, serials: Sequence[str]) -> str:
    """A config file for these SL V3 panels, with the layout they get by default with the config's sources."""
    panels = tuple(Entry("slv3", {"serial": serial}, str(i + 1)) for i, serial in enumerate(serials))
    specs = layout(replace(config, panels=panels, layout=()), catalog(config)).default
    lines = [f"layout = [{', '.join(map(json.dumps, specs))}]"]
    for serial in serials:
        lines += ["", "[[panels]]", f"serial = {json.dumps(serial)}"]
    return "\n".join(lines) + "\n"


def devices(config: Config) -> list[tuple[str, Device]]:
    return [(e.name, build("devices", Device, DEVICES, e, f"panels[{i}]")) for i, e in enumerate(config.panels)]


def sources(config: Config) -> list[tuple[str, Source]]:
    return [(e.name, build("sources", Source, SOURCES, e, f"sources[{i}]")) for i, e in enumerate(config.sources)]


def build[C](kind: str, base: type[C], builtin: Mapping[str, type[C]], e: Entry, where: str) -> C:
    """The class an entry names, made with its options."""
    try:
        cls = plugins.resolve(kind, base, builtin, e.kind)
    except plugins.PluginError as error:
        raise ConfigError(f"{where}: {error}") from None
    params = inspect.signature(cls).parameters.values()
    takes = [p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    if (unknown := [k for k in e.options if k not in takes]) and all(p.kind != p.VAR_KEYWORD for p in params):
        raise ConfigError(f"{where}: {e.kind} takes no {unknown[0]!r} (it takes {', '.join(takes) or 'nothing'})")
    if needed := [p.name for p in params if p.name in takes and p.default is p.empty and p.name not in e.options]:
        raise ConfigError(f"{where}: {e.kind} needs {', '.join(needed)}")
    try:
        return cls(**e.options)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{where}: {error}") from None


def runner(config: Config, report: Report) -> Runner:
    """Everything `run` needs, checked before anything opens."""
    if not config.panels:
        raise ConfigError(f"no [[panels]] (`{NAME} devices` lists the panels attached)")
    found = catalog(config)
    built = sources(config)
    plan = layout(config, found, built)
    screens = [Screen(name, device, report) for name, device in devices(config)]
    feed = Feed(config.readings, {spec for cls in found.designs.values() for spec in cls.trails})
    return Runner(screens, Sampler(built, report), feed, found, plan, report)
