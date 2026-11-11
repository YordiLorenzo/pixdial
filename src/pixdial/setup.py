"""`setup`: from an installed pixdial to live panels. It finds the panels, gives this user access to them (the one
step that needs root, run through sudo after it prints the commands), writes the config and runs the doctor checks.
pixdial itself always runs as the user."""

from __future__ import annotations

import getpass
import grp
import os
import shlex
import subprocess
from pathlib import Path

from . import NAME, doctor, service
from . import config as cfg
from .devices import Slv3, slv3

GROUP = NAME  # the group the rule gives the panels to on a machine nobody logs in to
RULE = Path("/etc/udev/rules.d/60-pixdial.rules")
RULE_DIRS = (Path("/etc/udev/rules.d"), Path("/run/udev/rules.d"), Path("/usr/lib/udev/rules.d"))  # udev's order
USERS = Path("/run/systemd/users")  # logind's state per user; ACTIVE_SEATS: the seats of their active sessions


def rule(group: str | None) -> str:
    """The udev rule for every panel pixdial drives: for the user at the machine's seat (uaccess), or for a group."""
    access = f'GROUP="{group}", MODE="0660"' if group else 'TAG+="uaccess"'
    return "".join(
        f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{vendor:04x}", ATTRS{{idProduct}}=="{product:04x}", {access}\n'
        for vendor, product in slv3.USB_IDS
    )


def installed() -> list[str]:
    """The rule lines of the pixdial rule file udev reads (the first of that name in its order); [] if none."""
    for folder in RULE_DIRS:
        try:
            text = (folder / RULE.name).read_text()
        except FileNotFoundError:
            continue
        return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return []


def headless() -> bool:
    """Whether the panels need the group rule: the user's services start at boot (linger), or the user has no
    active session at a seat, which is whom the uaccess rule gives access."""
    try:
        state = (USERS / str(os.getuid())).read_text().splitlines()
    except OSError:  # no logind
        return True
    seats = next((line.partition("=")[2] for line in state if line.startswith("ACTIVE_SEATS=")), "")
    return service.lingers() or not seats.split()


def needs_group_rule() -> bool:
    """Whether a reboot would leave the panels shut to the service: a headless machine without the group rule."""
    return headless() and installed() != rule(GROUP).splitlines()


def script(group: str | None) -> str:
    """The commands that install the rule (and on a headless machine the group, with this user in it)."""
    who = f"members of the {group} group" if group else "the user at the machine"
    lines = []
    if group:
        lines += [f"getent group {group} >/dev/null || groupadd --system {group}"]
        lines += [f"usermod -aG {group} {shlex.quote(getpass.getuser())}"]
    lines += [f"cat > {RULE} <<'RULE'", f"# From `{NAME} setup`: lets {who} use the panels pixdial drives."]
    lines += [*rule(group).splitlines(), "RULE"]
    lines += ["udevadm control --reload-rules", "udevadm trigger --subsystem-match=usb --action=add", "udevadm settle"]
    return "\n".join(lines) + "\n"


def setup(path: Path | None, dry_run: bool) -> bool:
    """Whether it ends with every check passed."""
    if dry_run:
        print(f"Dry run: `{NAME} setup` writes nothing and runs nothing. This is what it would do.\n")
    found = Slv3.discover()
    if not found:
        print(f"No panels found. {slv3.CABLE}.")
        for product, port in doctor.others():
            print(f"{slv3.VENDOR:04x}:{product:04x} at usb {port}: {doctor.pointer(product)}")
        return False
    print(f"Found {len(found)} panel{'s' * (len(found) > 1)}: {', '.join(f'{f.id} at {f.where}' for f in found)}.")
    group = GROUP if headless() else None
    if not all(f.access for f in found) or needs_group_rule():
        if not grant(group, dry_run):
            return False
        found = Slv3.discover()
        if not dry_run:
            print(f"This user may open {sum(f.access for f in found)} of {len(found)} panels now.")
    if not write(path or cfg.config_path(), [f.id for f in found], dry_run):
        return False
    if dry_run:
        print("Then it runs the doctor checks (`pixdial doctor`).")
        return True
    print("\nChecks:")
    failed = 0
    for c in doctor.checks(path):
        failed += c.status == doctor.FAIL
        print(doctor.line(c), flush=True)
    if group and not member(group):
        print(f"\nYour user is in the {group} group from its next login. Log out and back in (on a machine with")
        print(f"linger, reboot), then run `{NAME} service install`.")
    elif not failed:
        print(f"\nNext: `{NAME} service install` shows them now and at every login.")
    return not failed


def member(group: str) -> bool:
    """Whether this process has the group (a group the user was just added to comes with the next login)."""
    try:
        return grp.getgrnam(group).gr_gid in os.getgroups()
    except KeyError:
        return False


def grant(group: str | None, dry_run: bool) -> bool:
    """Prints the rule's commands and runs them through sudo; whether they ran (or would, in a dry run)."""
    commands = script(group)
    if group is None:
        print("This user may not open the panels yet.")
    else:
        print("The service may start here with nobody at the machine (linger, or no login at its seat), so the")
        print(f"panels need a rule for the {group} group.")
    print("Setup runs these commands as root, through sudo (it asks for your password):\n")
    print(indented(f"sudo sh -e <<'SETUP'\n{commands}SETUP\n"))
    if dry_run:
        return True
    if subprocess.run(["sudo", "sh", "-e"], input=commands, text=True, check=False).returncode != 0:
        print(f"They did not all run: run the commands above yourself, then `{NAME} setup` again.")
        return False
    return True


def write(path: Path, serials: list[str], dry_run: bool) -> bool:
    """Writes the config for these panels, asking first if it would replace another; False if that was kept."""
    text = cfg.written(cfg.Config(path), serials)
    old = path.read_text() if path.exists() else None
    if old == text:
        print(f"{path} has these panels already.")
        return True
    if dry_run:
        print(f"It writes {path}{', after it asks to replace the one there' if old is not None else ''}:\n")
        print(indented(text))
        return True
    if old is not None and not ask(f"{path} exists. Replace it with a config for these panels? [y/N] "):
        print(f"kept {path}. A config for these panels:\n\n{text}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"Wrote {path}.")
    return True


def indented(text: str) -> str:
    return "".join(f"  {line}\n" if line else "\n" for line in text.splitlines())


def ask(question: str) -> bool:
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:  # no terminal
        return False
