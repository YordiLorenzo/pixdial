"""`doctor`: whether everything `run` needs is in place, without opening a panel. `doctor --share`: the same with
the machine's details, as Markdown for an issue, with serials, the hostname and the home folder taken out."""

from __future__ import annotations

import contextlib
import platform
import re
import socket
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import PIL
from PIL import features

from . import NAME, __version__, plugins
from . import config as cfg
from .designs import BUILTIN as DESIGNS
from .designs import Design
from .designs.geometry import FONTS
from .devices import BUILTIN as DEVICES
from .devices import Device, Found, Slv3, slv3, usbfs
from .readings import Reading
from .sources import BUILTIN as SOURCES
from .sources import Source, hwmon

OK, SKIP, FAIL = "ok", "skip", "FAIL"
NO_RAQM = "Text is set without the font's kerning, a little wider. For raqm, install FriBiDi (fribidi or libfribidi0)."
HINTS = {  # why a default source gives nothing on many machines, and what follows
    "rapl": "cpu_w (the CPU's power) needs read access to the RAPL counter, which only root has by default.",
    "nvml": "No NVIDIA driver: the GPU readings come from it, so gpu and twin are left out of the rotation.",
    "hwmon": "No k10temp or coretemp sensor: name your CPU's in [[sources]] (docs/config.md#sources).",
}
TURING = {0x0028, 0x0046, 0x0050, 0x0080, 0x0088, 0x0092, 0x0123}  # Turing and TURZX screens, on Lian Li's vendor id


@dataclass(frozen=True)
class Check:
    what: str
    status: str  # OK; SKIP: missing, and pixdial runs without it; FAIL
    detail: str
    hint: str = ""  # what to do about it, in lines under it
    readings: Mapping[str, Reading] = field(default_factory=dict)  # a source's, as it gave them


def line(c: Check) -> str:
    """A check as `doctor` prints it."""
    return f"{c.status:4}  {c.what:16} {c.detail}".rstrip() + "".join(
        f"\n      {hint}".rstrip(" ") for hint in c.hint.splitlines()
    )


def checks(path: Path | None, wait: Callable[[float], None] = time.sleep) -> Iterator[Check]:
    """Each check as it is done; the sources are read twice, a second apart (a load or power needs two samples)."""
    yield Check(NAME, OK, f"{__version__} (to upgrade: {upgrade()})")
    try:
        config = cfg.load(path)
    except cfg.ConfigError as error:
        yield Check("config", FAIL, f"{path or cfg.config_path()}: {error}")
        return
    exists = config.path.exists()
    yield Check("config", OK, str(config.path) if exists else f"none at {config.path}: the defaults")
    missing = [w for w in ("Black", "Bold", "Regular") if not (FONTS / f"Lato-{w}.ttf").exists()]
    yield Check("fonts", FAIL if missing else OK, f"missing Lato {', '.join(missing)}" if missing else str(FONTS))
    yield Check("raqm", OK, "yes") if features.check_feature("raqm") else Check("raqm", SKIP, "no", NO_RAQM)
    for kind, base, builtin in (
        ("designs", Design, DESIGNS),
        ("sources", Source, SOURCES),
        ("devices", Device, DEVICES),
    ):
        for name, why in plugins.available(kind, base, builtin)[1].items():
            yield Check(f"plugin {name}", FAIL, why)
    yield from panels(config)
    try:
        built = cfg.sources(config)  # built once: a plugin's source may hold a device until it is closed
    except cfg.ConfigError as error:
        yield Check("sources", FAIL, str(error))
        return
    yield from layout(config, built)
    yield from sources(config, built, wait)


def upgrade() -> str:
    """The command that upgrades this copy of pixdial, from where it is installed."""
    prefix = Path(sys.prefix).as_posix()
    if "/uv/tools/" in prefix:
        return f"uv tool upgrade {NAME}"
    if "/pipx/venvs/" in prefix:
        return f"pipx upgrade {NAME}"
    if prefix.startswith("/nix/store/"):
        return "update your Nix profile or system"
    if sys.prefix == sys.base_prefix:  # no virtual environment: a distribution's package
        return f"your package manager's upgrade, such as yay -Syu {NAME}"
    return f"pip install --upgrade {NAME}"


def panels(config: cfg.Config) -> Iterator[Check]:
    if not config.panels:
        yield unconfigured(config)
        return
    try:
        devices = cfg.devices(config)
    except cfg.ConfigError as error:
        yield Check("panels", FAIL, str(error))
        return
    for name, device in devices:
        problem = device.problem()
        yield Check(f"panel {name}", FAIL if problem else OK, problem or "attached, and this user may open it")


def unconfigured(config: cfg.Config) -> Check:
    """No [[panels]] yet: the SL V3 panels attached, and the config that shows on them."""
    serials = [found.id for found in Slv3.discover()]
    if not serials:
        return Check("panels", FAIL, "none in the config, and none attached", f"{slv3.CABLE}.")
    snippet = cfg.written(config, serials)
    hint = f"`{NAME} setup` writes this config, or put it in {config.path}:\n\n{snippet}"
    return Check("panels", SKIP, f"none in the config yet; {len(serials)} attached", hint)


def layout(config: cfg.Config, built: Sequence[tuple[str, Source]]) -> Iterator[Check]:
    try:
        catalog = cfg.catalog(config)
        specs = cfg.layout(config, catalog, built).load()
        left_out = {} if config.rotation and config.layout else cfg.skipped(catalog, built)
    except (cfg.ConfigError, ValueError) as error:
        yield Check("layout", FAIL, str(error))
        return
    yield Check("layout", OK, " ".join(specs))
    if left_out:
        keys = list(dict.fromkeys(key for missing in left_out.values() for key in missing))
        unfed = f"{', '.join(keys[:-1])} or {keys[-1]}" if len(keys) > 1 else keys[0]
        detail = f"the default rotation leaves out {', '.join(left_out)}: no source gives {unfed}"
        hint = "A source for those readings brings them back (docs/config.md#sources); `rotation` names any design."
        yield Check("designs", SKIP, detail, hint)


def sources(config: cfg.Config, built: Sequence[tuple[str, Source]], wait: Callable[[float], None]) -> Iterator[Check]:
    optional = config.sources == cfg.DEFAULT_SOURCES  # the config names none, and pixdial runs without each
    for _, source in built:  # a first sample: a load or a power is a change between two
        with contextlib.suppress(Exception):  # the second read reports it
            source.read()
    wait(1.0)
    for name, source in built:
        try:
            readings = source.read()
        except Exception as error:
            message = str(error) or repr(error)
            yield (
                Check(f"source {name}", SKIP, message, HINTS.get(name, ""))
                if optional
                else Check(f"source {name}", FAIL, message)
            )
            continue
        finally:
            source.close()
        given = ", ".join(describe(k, r) for k, r in readings.items()) or "nothing yet"
        yield Check(f"source {name}", OK, given, readings=readings)


def describe(key: str, r: Reading) -> str:
    unit = f" {r.unit}" if r.unit and r.unit != "%" else r.unit
    if np.ndim(r.value):
        values = np.asarray(r.value)
        return f"{key} {len(values)} values {values.min():.0f}-{values.max():.0f}{unit}"
    limit = f" (max {r.max:.0f})" if r.max else ""
    return f"{key} {float(r.value):.1f}".removesuffix(".0") + f"{unit}{limit}"


def others() -> list[tuple[int, str]]:
    """The product id and USB port of each device with Lian Li's vendor id that pixdial doesn't drive."""
    driven = {product for vendor, product in slv3.USB_IDS if vendor == slv3.VENDOR}
    return [(product, port) for product, port in usbfs.products(slv3.VENDOR) if product not in driven]


def pointer(product: int) -> str:
    """Where to look for a program that drives a device with Lian Li's vendor id that pixdial doesn't."""
    if product in TURING:
        return (
            "a Turing or TURZX screen: turing-smart-screen-python drives those "
            "(https://github.com/mathoudebine/turing-smart-screen-python)"
        )
    return "not a panel pixdial drives: lian-li-linux drives most Lian Li devices (https://github.com/sgtaziz/lian-li-linux)"


# ---------------------------------------------------------------- --share


def share(path: Path | None) -> str:
    """The checks and the machine's details as Markdown to paste in an issue. It opens each free panel this user
    may open for a moment, for its firmware, and leaves it dark."""
    done = list(checks(path))
    attached = Slv3.discover()
    try:
        configured = [str(e.options.get("serial", "")) for e in cfg.load(path).panels]
    except cfg.ConfigError:  # its error can quote a panel's table, serial and all
        where = path or cfg.config_path()
        try:
            text = where.read_text()
        except OSError:  # missing or unreadable: its error, in the checks, quotes no table
            text = ""
        configured = re.findall(r"""serial\s*=\s*["']([^"']+)["']""", text)
    given = {key for c in done for key in c.readings}
    raqm = "yes" if features.check_feature("raqm") else "no"
    ids = [
        f"- {slv3.VENDOR:04x}:{product:04x} at usb {port}"
        + (f": {pointer(product)}" if (slv3.VENDOR, product) not in slv3.USB_IDS else "")
        for product, port in usbfs.products(slv3.VENDOR)
    ]
    panels = [f"- {found.id} at {found.where}: {firmware(found)}" for found in attached]
    chips = [
        f"- {chip}: {', '.join(describe(k, r) for k, r in sensors.items())}"
        for chip, sensors in hwmon.chips()
        if sensors  # a chip with no readings (asus beside asusec) says nothing
    ]
    designs = plugins.available("designs", Design, DESIGNS)[0]
    misses = {name: [key for key in cls.reads if key not in given] for name, cls in designs.items()}
    text = "\n".join(
        [
            f"### {NAME} doctor --share",
            "",
            f"- {NAME} {__version__}, Python {platform.python_version()}, Pillow {PIL.__version__} (raqm {raqm})",
            f"- {distro()}, kernel {platform.release()}",
            "",
            f"USB devices with Lian Li's vendor id ({slv3.VENDOR:04x}):",
            "",
            *(ids or ["- none"]),
            "",
            "Panels:",
            "",
            *(panels or ["- none attached"]),
            "",
            "Checks:",
            "",
            "```text",
            *map(line, done),
            "```",
            "",
            "hwmon:",
            "",
            *(chips or ["- none"]),
            "",
            "Readings the designs miss:",
            "",
            *([f"- {name}: {', '.join(keys)}" for name, keys in misses.items() if keys] or ["- none"]),
            "",
        ]
    )
    return private(text, [found.id for found in attached] + configured)


def firmware(found: Found) -> str:
    """What a free panel says about itself when opened (its firmware), or why it can't be opened now."""
    if found.held:
        return f"in use by {found.held}"
    if not found.access:
        return "no access"
    panel = Slv3(found.id)
    try:
        about = panel.open()
    except OSError as error:
        return f"could not open it: {error}"
    with contextlib.suppress(OSError):
        panel.off()  # dark, as `run` leaves it
    panel.close()
    return about


def distro() -> str:
    try:
        return platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except OSError:
        return "an unknown system"


def private(text: str, serials: Sequence[str]) -> str:
    """The text with each serial as panel-1, panel-2 (in the order given), the home folder as ~ and the hostname
    as host."""
    for i, serial in enumerate(dict.fromkeys(s for s in serials if s), 1):
        text = text.replace(serial, f"panel-{i}")
    text = text.replace(str(Path.home()), "~")
    host = socket.gethostname()
    for name in dict.fromkeys((host, host.split(".")[0])):
        if name:
            text = re.sub(rf"\b{re.escape(name)}\b", "host", text)
    return text
