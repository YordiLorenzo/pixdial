"""`service`: the systemd user unit the wheel ships, installed for the pixdial that runs now."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from . import NAME

UNIT = f"{NAME}.service"
LINGER = Path("/var/lib/systemd/linger")  # logind's mark, a file per user, that the user's services start at boot


def path() -> Path:
    """Where systemd looks for the user's own units."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user" / UNIT


def unit(config: Path | None) -> str:
    """The bundled unit with ExecStart pointed at this pixdial (a uv tool, pipx, AUR or Nix install each puts it
    somewhere else), and at the config it was given."""
    command = [str(Path(sys.argv[0]).resolve())]
    if config is not None:
        command += ["--config", str(config.resolve())]
    text = (files(NAME) / "data" / UNIT).read_text()
    start = f"ExecStart={' '.join(map(quoted, command))} run"
    return "".join(f"{start}\n" if line.startswith("ExecStart=") else line for line in text.splitlines(True))


def quoted(word: str) -> str:
    """One ExecStart word as systemd reads it: % and $ doubled, and in double quotes with \\ and " escaped where it
    holds a space, a quote or a backslash, so a path such as "panel configs/config.toml" stays one argument."""
    word = word.replace("%", "%%").replace("$", "$$")
    if not any(c in word for c in " \t\"'\\"):
        return word
    return '"' + word.replace("\\", "\\\\").replace('"', '\\"') + '"'


def install(config: Path | None) -> Path:
    """Writes the unit, then enables it and starts it, or restarts it so a new ExecStart or pixdial takes effect."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(unit(config))
    systemctl("daemon-reload")
    systemctl("enable", UNIT)
    systemctl("restart", UNIT)
    return target


def remove() -> bool:
    """Stops and disables the unit and deletes it; False if there is none to delete."""
    target = path()
    if not target.exists():
        return False
    systemctl("disable", "--now", UNIT)
    target.unlink()
    systemctl("daemon-reload")
    return True


def status() -> int:
    """systemctl's status of the unit, printed as it prints it: 0 while it runs."""
    return subprocess.run(["systemctl", "--user", "--no-pager", "status", UNIT], check=False).returncode


def lingers() -> bool:
    """Whether the user's services start at boot, before anyone logs in (`loginctl enable-linger`)."""
    return (LINGER / getpass.getuser()).exists()


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", "--user", *args], check=True)
