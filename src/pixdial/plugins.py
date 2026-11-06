"""Finding designs, sources and devices: the built-in ones, installed plugins, and local code.

A plugin package registers its classes as entry points in the groups "pixdial.designs", "pixdial.sources" and
"pixdial.devices" (the name before ".designs" is the project's NAME). Code that isn't installed can be named in the
config as "module:Class", for a module on the Python path.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from importlib.metadata import entry_points

from . import NAME


class PluginError(LookupError):
    pass


def available[C](kind: str, base: type[C], builtin: Mapping[str, type[C]]) -> tuple[dict[str, type[C]], dict[str, str]]:
    """The built-in classes of a kind ("designs", "sources" or "devices") and the installed plugins' (a plugin never
    replaces a built-in one), and the plugins that failed to load, with why."""
    found, broken = dict(builtin), {}
    for ep in entry_points(group=f"{NAME}.{kind}"):
        if ep.name in found:
            broken[ep.name] = f"{ep.value}: a built-in {kind[:-1]} has that name"
            continue
        try:
            found[ep.name] = checked(ep.load(), base, ep.value)
        except Exception as error:  # a broken plugin must not take the others down
            broken[ep.name] = f"{ep.value}: {error}"
    return found, broken


def resolve[C](kind: str, base: type[C], builtin: Mapping[str, type[C]], name: str) -> type[C]:
    """A class by its name, or by "module:Class"."""
    if ":" in name:
        module, _, attr = name.partition(":")
        try:
            return checked(getattr(importlib.import_module(module), attr), base, name)
        except (ImportError, AttributeError) as error:
            raise PluginError(f"{name}: {error}") from error
    found, broken = available(kind, base, builtin)
    if name in found:
        return found[name]
    if name in broken:
        raise PluginError(f"{kind[:-1]} {name!r} failed to load: {broken[name]}")
    raise PluginError(f"no {kind[:-1]} {name!r} ({kind}: {', '.join(found)})")


def checked[C](obj: object, base: type[C], where: str) -> type[C]:
    if not (isinstance(obj, type) and issubclass(obj, base)):
        raise PluginError(f"{where} is not a {base.__name__}")
    return obj
