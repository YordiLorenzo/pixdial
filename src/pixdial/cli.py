"""The command line. Exit codes: 0 done, 1 a check or a search came up short, 2 a usage or config error."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from . import NAME, __version__, demo, doctor, plugins, service, setup
from . import config as cfg
from .designs import BUILTIN as DESIGNS
from .designs import THEMES, Design
from .devices import BUILTIN as DEVICES
from .devices import Device, slv3
from .gallery import Demo, gallery
from .runtime import ROTATE, Report
from .sources import BUILTIN as SOURCES
from .sources import Source

OK, SHORT, USAGE = 0, 1, 2


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.command(args))
    except cfg.ConfigError as error:
        print(f"{NAME}: {args.config or cfg.config_path()}: {error}", file=sys.stderr)
        return USAGE


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=NAME, description="A Python SDK and CLI for hardware screens on Linux.")
    p.add_argument("--version", action="version", version=f"{NAME} {__version__}")
    p.add_argument("--config", type=Path, help=f"the config file (default {cfg.config_path()})")
    sub = p.add_subparsers(required=True, metavar="COMMAND")

    run_ = sub.add_parser("run", help="show the designs on the panels until stopped")
    run_.set_defaults(command=run)

    show_ = sub.add_parser("show", help="pick the designs a running `run` shows; alone, the current ones")
    show_.add_argument("specs", nargs="*", metavar="DESIGN", help=f"one per panel (name or name:theme), or {ROTATE}")
    show_.set_defaults(command=show)

    list_ = sub.add_parser("list", help="the designs, themes, sources and devices")
    list_.set_defaults(command=list_all)

    devices_ = sub.add_parser("devices", help="the panels attached now")
    devices_.set_defaults(command=devices)

    render_ = sub.add_parser("render", help="designs as PNG files from demo readings, without hardware")
    render_.add_argument("specs", nargs="*", metavar="DESIGN", help="name or name:theme (default: every design)")
    render_.add_argument("--state", default="busy", choices=demo.STATES, help="the demo readings (default busy)")
    render_.add_argument("--scale", type=int, default=1, choices=(1, 2, 3, 4), help="1 is the panel's 400 px")
    render_.add_argument("--out", type=Path, default=Path(), help="the folder to write to (default here)")
    render_.add_argument("--gallery", type=Path, metavar="DIR", help="every design, sheets and gallery.html, to DIR")
    render_.set_defaults(command=render)

    doctor_ = sub.add_parser("doctor", help="check the config, panels, permissions and sources")
    doctor_.add_argument("--share", action="store_true", help="the same as Markdown for an issue, without serials")
    doctor_.set_defaults(command=check)
    service_parser(sub)
    setup_parser(sub)
    return p


def run(args: argparse.Namespace) -> int:
    runner = cfg.runner(cfg.load(args.config), Report())
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    runner.run(stop)
    return OK


def show(args: argparse.Namespace) -> int:
    config = cfg.load(args.config)
    layout = cfg.layout(config, cfg.catalog(config))
    if args.specs:
        try:
            layout.save(args.specs)
        except ValueError as error:
            print(f"{NAME}: {error}; the panels keep {' '.join(layout.load())}", file=sys.stderr)
            return USAGE
    print(" ".join(layout.load()))
    return OK


def list_all(args: argparse.Namespace) -> int:
    config = cfg.load(args.config)
    designs, broken = plugins.available("designs", Design, DESIGNS)
    print("designs:")
    for name, cls in designs.items():
        print(f"  {name:10} {cls.shows}{f' (animated, {cls.fps} frames/s)' if cls.fps else ''}")
    print(f"themes: {', '.join(THEMES)} (name:theme; {config.theme} is the default)")
    for kind, base, builtin in (("sources", Source, SOURCES), ("devices", Device, DEVICES)):
        found, more = plugins.available(kind, base, builtin)
        print(f"{kind}: {', '.join(found)}")
        broken |= more
    for name, why in broken.items():
        print(f"broken plugin {name}: {why}", file=sys.stderr)
    return OK


def devices(args: argparse.Namespace) -> int:
    panels = {device.id: name for name, device in cfg.devices(cfg.load(args.config))}
    found = 0
    for kind, cls in plugins.available("devices", Device, DEVICES)[0].items():
        for panel in cls.discover():
            found += 1
            access = f"in use by {panel.held}" if panel.held else "ok"
            access = access if panel.access else f"no access (`{NAME} setup` gives it)"
            where = f"panel {panels[panel.id]!r}" if panel.id in panels else "not in the config"
            print(f"{kind}  {panel.id}  {panel.where}  {access}  {where}")
    for product, port in doctor.others():
        print(f"{slv3.VENDOR:04x}:{product:04x}  usb {port}  {doctor.pointer(product)}")
    if not found:
        print(f"no panels attached. {slv3.CABLE}", file=sys.stderr)
    return OK if found else SHORT


def render(args: argparse.Namespace) -> int:
    config = cfg.load(args.config)
    catalog = cfg.catalog(config)
    if args.gallery:
        gallery(args.gallery, catalog, config.readings)
        print(args.gallery / "gallery.html")
        return OK
    specs = args.specs or list(catalog.designs)
    for spec in specs:
        try:
            catalog.check(spec)
        except ValueError as error:
            print(f"{NAME}: {error}", file=sys.stderr)
            return USAGE
    args.out.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        path = args.out / f"{spec.replace(':', '-')}-{args.state}@{args.scale}x.png"
        Demo(catalog.make(spec, args.scale), args.state, config.readings).render().save(path)
        print(path)
    return OK


def check(args: argparse.Namespace) -> int:
    if args.share:
        print(doctor.share(args.config))
        return OK
    failed = 0
    for c in doctor.checks(args.config):
        failed += c.status == doctor.FAIL
        print(doctor.line(c), flush=True)
    return OK if not failed else SHORT


def service_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    service_ = sub.add_parser("service", help="run `run` at every login, as a systemd user service")
    actions = service_.add_subparsers(required=True, metavar="ACTION")
    for name, command, about in (
        ("install", service_install, "install the unit for this pixdial, enable it and start it"),
        ("remove", service_remove, "stop it, disable it and delete the unit"),
        ("status", service_status, "systemctl's status of it, with its last log lines"),
    ):
        actions.add_parser(name, help=about).set_defaults(command=systemctl_errors(command))


def systemctl_errors(command: Callable[[argparse.Namespace], int]) -> Callable[[argparse.Namespace], int]:
    """The command, with a failed or missing systemctl as one line and exit status 1."""

    def checked(args: argparse.Namespace) -> int:
        try:
            return command(args)
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"{NAME}: {error}", file=sys.stderr)
            return SHORT

    return checked


def service_install(args: argparse.Namespace) -> int:
    path = service.install(args.config)
    print(f"wrote {path}, enabled and started it: `run` now starts at every login")
    if setup.needs_group_rule():
        print(f"With nobody at the machine after a reboot, it can't open the panels: `{NAME} setup` gives them a")
        print("rule that works then")
    elif not service.lingers():
        print(f"To start it at boot, before you log in: loginctl enable-linger, then `{NAME} setup` again")
    return OK


def service_remove(args: argparse.Namespace) -> int:
    if not service.remove():
        print(f"{NAME}: no unit at {service.path()}", file=sys.stderr)
        return SHORT
    print(f"stopped and disabled {service.UNIT}, and deleted {service.path()}")
    return OK


def service_status(args: argparse.Namespace) -> int:
    return OK if service.status() == 0 else SHORT


def setup_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup_ = sub.add_parser("setup", help="find the panels, give this user access, write the config and check it")
    setup_.add_argument("--dry-run", action="store_true", help="print what it would do; write and run nothing")
    setup_.set_defaults(command=set_up)


def set_up(args: argparse.Namespace) -> int:
    return OK if setup.setup(args.config, args.dry_run) else SHORT
