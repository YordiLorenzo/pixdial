"""`doctor`: whether everything `run` needs is in place, without opening a panel."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import features

from . import config as cfg
from . import plugins
from .designs import BUILTIN as DESIGNS
from .designs import Design
from .designs.geometry import FONTS
from .devices import BUILTIN as DEVICES
from .devices import Device
from .readings import Reading
from .sources import BUILTIN as SOURCES
from .sources import Source

NO_RAQM = "digits may change width as they count (install FriBiDi: the fribidi or libfribidi0 package)"


@dataclass(frozen=True)
class Check:
    what: str
    ok: bool
    detail: str


def checks(path: Path | None, wait: Callable[[float], None] = time.sleep) -> Iterator[Check]:
    """Each check as it is done; the sources are read twice, a second apart (a load or power needs two samples)."""
    try:
        config = cfg.load(path)
    except cfg.ConfigError as error:
        yield Check("config", False, f"{path or cfg.config_path()}: {error}")
        return
    exists = config.path.exists()
    yield Check("config", True, str(config.path) if exists else f"none at {config.path}: the defaults")
    missing = [w for w in ("Black", "Bold", "Regular") if not (FONTS / f"Lato-{w}.ttf").exists()]
    yield Check("fonts", not missing, f"missing Lato {', '.join(missing)}" if missing else str(FONTS))
    yield Check("raqm", True, "yes" if features.check_feature("raqm") else f"no: {NO_RAQM}")
    for kind, base, builtin in (
        ("designs", Design, DESIGNS),
        ("sources", Source, SOURCES),
        ("devices", Device, DEVICES),
    ):
        for name, why in plugins.available(kind, base, builtin)[1].items():
            yield Check(f"plugin {name}", False, why)
    yield from panels(config)
    yield from layout(config)
    yield from sources(config, wait)


def panels(config: cfg.Config) -> Iterator[Check]:
    if not config.panels:
        yield Check("panels", False, "no [[panels]] in the config (`devices` lists the panels attached)")
        return
    try:
        devices = cfg.devices(config)
    except cfg.ConfigError as error:
        yield Check("panels", False, str(error))
        return
    for name, device in devices:
        problem = device.problem()
        yield Check(f"panel {name}", problem is None, problem or "attached, and this user may open it")


def layout(config: cfg.Config) -> Iterator[Check]:
    try:
        catalog = cfg.catalog(config)
        specs = cfg.layout(config, catalog).load()
        left_out = {} if config.rotation and config.layout else cfg.skipped(config, catalog)
    except (cfg.ConfigError, ValueError) as error:
        yield Check("layout", False, str(error))
        return
    yield Check("layout", True, " ".join(specs))
    if left_out:
        keys = list(dict.fromkeys(key for missing in left_out.values() for key in missing))
        unfed = f"{', '.join(keys[:-1])} or {keys[-1]}" if len(keys) > 1 else keys[0]
        yield Check("designs", True, f"the default rotation leaves out {', '.join(left_out)}: no source gives {unfed}")


def sources(config: cfg.Config, wait: Callable[[float], None]) -> Iterator[Check]:
    try:
        built = cfg.sources(config)
    except cfg.ConfigError as error:
        yield Check("sources", False, str(error))
        return
    for _, source in built:  # a first sample: a load or a power is a change between two
        with contextlib.suppress(Exception):  # the second read reports it
            source.read()
    wait(1.0)
    for name, source in built:
        try:
            readings = source.read()
        except Exception as error:
            yield Check(f"source {name}", False, str(error) or repr(error))
            continue
        finally:
            source.close()
        yield Check(f"source {name}", True, ", ".join(describe(k, r) for k, r in readings.items()) or "nothing yet")


def describe(key: str, r: Reading) -> str:
    unit = f" {r.unit}" if r.unit and r.unit != "%" else r.unit
    if np.ndim(r.value):
        values = np.asarray(r.value)
        return f"{key} {len(values)} values {values.min():.0f}-{values.max():.0f}{unit}"
    limit = f" (max {r.max:.0f})" if r.max else ""
    return f"{key} {float(r.value):.1f}".removesuffix(".0") + f"{unit}{limit}"
