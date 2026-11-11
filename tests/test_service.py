"""`pixdial service`: the user unit it writes and the systemctl calls it makes, against a fake systemctl."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pixdial import service
from pixdial.cli import main


@pytest.fixture
def systemctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A systemctl on PATH that logs each call's arguments as a line and exits with $STATUS; the log's path."""
    log, bin_ = tmp_path / "systemctl.log", tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "systemctl"
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit "${{STATUS:-0}}"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return log


@pytest.fixture
def pixdial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The running pixdial as a link in a bin folder to the tool's own copy, as `uv tool install` leaves it."""
    tool = tmp_path / "tools" / "pixdial" / "bin" / "pixdial"
    tool.parent.mkdir(parents=True)
    tool.write_text("")
    link = tmp_path / "local-bin" / "pixdial"
    link.parent.mkdir()
    link.symlink_to(tool)
    monkeypatch.setattr(sys, "argv", [str(link), "service", "install"])
    return tool.resolve()


def unit(tmp_path: Path) -> Path:
    return tmp_path / "config" / "systemd" / "user" / "pixdial.service"


def test_install_points_the_unit_at_this_pixdial_and_starts_it(
    tmp_path: Path, systemctl: Path, pixdial: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["service", "install"]) == 0
    text = unit(tmp_path).read_text()
    assert f"\nExecStart={pixdial} run\n" in text
    assert "%h/.local/bin" not in text
    assert "\nRestartPreventExitStatus=2\n" in text  # a config error (exit status 2) stops it once
    assert systemctl.read_text().splitlines() == [
        "--user daemon-reload",
        "--user enable pixdial.service",
        "--user restart pixdial.service",  # a new ExecStart or a new pixdial takes effect at once
    ]
    assert str(unit(tmp_path)) in capsys.readouterr().out


def test_install_passes_the_config_it_was_given(
    tmp_path: Path, systemctl: Path, pixdial: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["--config", "mine.toml", "service", "install"]) == 0
    assert f"\nExecStart={pixdial} --config {tmp_path.resolve() / 'mine.toml'} run\n" in unit(tmp_path).read_text()


def test_remove_stops_it_and_deletes_the_unit(tmp_path: Path, systemctl: Path, pixdial: Path) -> None:
    assert main(["service", "install"]) == 0
    systemctl.unlink()
    assert main(["service", "remove"]) == 0
    assert not unit(tmp_path).exists()
    assert systemctl.read_text().splitlines() == ["--user disable --now pixdial.service", "--user daemon-reload"]


def test_remove_without_a_unit_calls_nothing(systemctl: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["service", "remove"]) == 1
    assert "no unit at" in capsys.readouterr().err
    assert not systemctl.exists()


def test_status_is_systemctls(systemctl: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert main(["service", "status"]) == 0
    assert systemctl.read_text() == "--user --no-pager status pixdial.service\n"
    monkeypatch.setenv("STATUS", "3")  # inactive
    assert main(["service", "status"]) == 1


def test_a_failed_systemctl_is_reported(
    tmp_path: Path, systemctl: Path, pixdial: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STATUS", "1")
    assert main(["service", "install"]) == 1
    assert "daemon-reload" in capsys.readouterr().err
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))  # no systemd
    assert main(["service", "install"]) == 1
    assert "systemctl" in capsys.readouterr().err


def test_a_path_with_a_space_or_a_percent_stays_one_argument() -> None:
    assert service.quoted("/home/u/.local/bin/pixdial") == "/home/u/.local/bin/pixdial"
    assert service.quoted("/home/u/panel configs/config.toml") == '"/home/u/panel configs/config.toml"'
    assert service.quoted("/home/u/100%/a$b") == "/home/u/100%%/a$$b"
    assert service.quoted('/home/u/a "b"\\c') == '"/home/u/a \\"b\\"\\\\c"'


def test_python_m_pixdial_gets_a_unit_that_runs_the_same_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["/venv/lib/python3.14/site-packages/pixdial/__main__.py", "service", "install"])
    start = next(line for line in service.unit(None).splitlines() if line.startswith("ExecStart="))
    assert start == f"ExecStart={sys.executable} -m pixdial run"
