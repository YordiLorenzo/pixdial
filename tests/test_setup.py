"""`pixdial setup`: the udev rule it runs through sudo (a fake one here), the config it writes and when it asks."""

from __future__ import annotations

import builtins
import functools
import getpass
import os
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from pixdial import doctor, service, setup
from pixdial.cli import main
from pixdial.devices import Found, Slv3

A, B = "SERIALAAA111", "SERIALBBB222"


class Machine:
    """A fake machine's state: whether the user is at its seat or lingers, its rule files, and what sudo ran."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.users, self.linger, self.etc = root / "run-users", root / "linger", root / "etc-rules"
        self.sudo_log, self.sudo_script = root / "sudo.log", root / "sudo.script"
        for d in (self.users, self.linger, self.etc):
            d.mkdir()

    def at_seat(self) -> None:
        (self.users / str(os.getuid())).write_text("NAME=u\nSTATE=active\nACTIVE_SESSIONS=2\nACTIVE_SEATS=seat0\n")

    def lingers(self) -> None:
        (self.linger / getpass.getuser()).write_text("")

    def granted(self) -> bool:
        """Whether sudo ran the rule: the fake udev then gives this user access."""
        return self.sudo_script.exists()

    def config(self) -> Path:
        return self.root / "config" / "pixdial" / "config.toml"


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Machine:
    m = Machine(tmp_path)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    sudo = bin_ / "sudo"
    sudo.write_text(f'#!/bin/sh\necho "$@" >> "{m.sudo_log}"\ncat > "{m.sudo_script}"\nexit "${{SUDO_STATUS:-0}}"\n')
    sudo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(setup, "USERS", m.users)
    monkeypatch.setattr(service, "LINGER", m.linger)
    monkeypatch.setattr(setup, "RULE_DIRS", (m.etc, tmp_path / "usr-lib-rules"))
    monkeypatch.setattr(doctor, "checks", functools.partial(doctor.checks, wait=lambda s: None))
    panels = [(A, "usb 1-2 (/dev/bus/usb/001/005)"), (B, "usb 1-3 (/dev/bus/usb/001/006)")]
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: [Found(s, w, m.granted()) for s, w in panels]))
    return m


def run(*args: str) -> int:
    return main(["setup", *args])


def test_at_the_seat_it_runs_the_uaccess_rule_through_sudo_and_writes_the_config(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    machine.at_seat()
    assert run() == 0
    out = capsys.readouterr().out
    script = machine.sudo_script.read_text()
    assert machine.sudo_log.read_text() == "sh -e\n"  # one sudo, so one password prompt
    rule = setup.rule(None).rstrip("\n")
    assert 'ATTRS{idProduct}=="0005", TAG+="uaccess"' in rule and 'ATTRS{idProduct}=="0006", TAG+="uaccess"' in rule
    assert "cat > /etc/udev/rules.d/60-pixdial.rules <<'RULE'\n" in script and f"\n{rule}\nRULE\n" in script
    assert "udevadm trigger --subsystem-match=usb --action=add" in script
    assert "usermod" not in script and "groupadd" not in script
    assert f"sudo sh -e <<'SETUP'\n{script}SETUP\n" in out.replace("\n  ", "\n")  # what it ran, printed first
    text = machine.config().read_text()
    assert text.count("[[panels]]") == 2 and f'serial = "{A}"' in text and f'serial = "{B}"' in text
    assert text.startswith("layout = [")
    assert "ok    panel 1" in out and "ok    panel 2" in out  # the doctor checks
    assert "pixdial service install" in out


@pytest.mark.parametrize("state", ["no seat", "linger"])
def test_a_headless_machine_gets_the_group_rule(
    machine: Machine, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    if state == "linger":
        machine.at_seat()
        machine.lingers()
    assert run() in (0, 1)
    script = machine.sudo_script.read_text()
    assert "getent group pixdial >/dev/null || groupadd --system pixdial\n" in script
    assert f"usermod -aG pixdial {getpass.getuser()}\n" in script
    assert 'ATTRS{idProduct}=="0005", GROUP="pixdial", MODE="0660"\n' in script
    assert "uaccess" not in script
    assert "next login" in capsys.readouterr().out


def test_with_access_and_the_right_rule_it_runs_no_sudo(machine: Machine) -> None:
    machine.at_seat()
    machine.sudo_script.write_text("")  # access already
    assert run() == 0
    assert not machine.sudo_log.exists()
    assert machine.config().exists()


def test_a_headless_machine_with_access_still_gets_the_group_rule_for_after_a_reboot(machine: Machine) -> None:
    machine.lingers()
    machine.sudo_script.write_text("")  # access now, through uaccess while the user is at the seat
    (machine.etc / "60-pixdial.rules").write_text(setup.rule(None))
    run()
    assert 'GROUP="pixdial"' in machine.sudo_script.read_text()
    machine.sudo_log.unlink()
    (machine.etc / "60-pixdial.rules").write_text(setup.rule(setup.GROUP))
    run()
    assert not machine.sudo_log.exists()


def test_dry_run_writes_nothing_and_runs_nothing(
    machine: Machine, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    machine.at_seat()
    monkeypatch.setattr(doctor, "checks", lambda *args, **kwargs: pytest.fail("ran the checks"))
    assert run("--dry-run") == 0
    out = capsys.readouterr().out
    assert not machine.sudo_log.exists() and not machine.config().exists()
    assert "sudo sh -e <<'SETUP'" in out and 'TAG+="uaccess"' in out
    assert f'serial = "{A}"' in out


def test_an_existing_config_is_replaced_only_on_a_yes(
    machine: Machine, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    machine.at_seat()
    machine.config().parent.mkdir(parents=True)
    machine.config().write_text('theme = "ice"\n')
    answers: list[str] = []
    monkeypatch.setattr(builtins, "input", lambda prompt: answers.pop(0))
    answers.append("")
    run()
    assert machine.config().read_text() == 'theme = "ice"\n'
    assert "kept" in capsys.readouterr().out
    answers.append("y")
    run()
    assert f'serial = "{A}"' in machine.config().read_text()
    monkeypatch.setattr(builtins, "input", lambda prompt: pytest.fail("asked about the config it would write"))
    run()  # the same config again: nothing to ask


def test_with_no_input_an_existing_config_is_kept(machine: Machine, monkeypatch: pytest.MonkeyPatch) -> None:
    machine.at_seat()
    machine.config().parent.mkdir(parents=True)
    machine.config().write_text('theme = "ice"\n')

    def no_terminal(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", no_terminal)
    run()
    assert machine.config().read_text() == 'theme = "ice"\n'


def test_a_failed_sudo_stops_it(
    machine: Machine, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    machine.at_seat()
    monkeypatch.setenv("SUDO_STATUS", "1")
    assert run() == 1
    assert "run the commands above yourself" in capsys.readouterr().out
    assert not machine.config().exists()


def test_with_no_panels_it_names_the_cable(
    machine: Machine, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: []))
    assert run() == 1
    assert "USB 2 header" in capsys.readouterr().out
    assert not machine.sudo_log.exists() and not machine.config().exists()


def test_the_rule_the_package_ships_is_the_one_setup_writes() -> None:
    shipped = (files("pixdial") / "data" / "60-pixdial.rules").read_text()
    lines = [line for line in shipped.splitlines() if line and not line.startswith("#")]
    assert lines == setup.rule(None).splitlines()


def test_service_install_says_when_a_headless_machine_needs_the_group_rule(
    machine: Machine, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    systemctl = tmp_path / "bin" / "systemctl"
    systemctl.write_text("#!/bin/sh\n")
    systemctl.chmod(0o755)
    monkeypatch.setattr(sys, "argv", [str(systemctl), "service", "install"])
    machine.lingers()
    assert main(["service", "install"]) == 0
    assert "pixdial setup" in capsys.readouterr().out
    (machine.etc / "60-pixdial.rules").write_text(setup.rule(setup.GROUP))
    assert main(["service", "install"]) == 0
    assert "pixdial setup" not in capsys.readouterr().out
