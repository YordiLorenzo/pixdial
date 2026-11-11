"""The command line: what it prints and its exit codes."""

from __future__ import annotations

import logging
import re
import signal
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image

from pixdial import __version__
from pixdial.cli import main

CONFIG = """sources = []
[[panels]]
name = "top"
device = "png"
path = "{}"
[[panels]]
device = "png"
path = "{}"
"""


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = tmp_path / "config.toml"
    path.write_text(CONFIG.format(tmp_path / "a.png", tmp_path / "b.png"))
    return path


def test_show_saves_a_layout_and_refuses_a_bad_one(config: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", str(config), "show"]) == 0
    assert capsys.readouterr().out == "crown gpu\n"
    assert main(["--config", str(config), "show", "orb", "clock:ice"]) == 0
    assert main(["--config", str(config), "show", "orb"]) == 2
    assert "1 designs for 2 panels; the panels keep orb clock:ice" in capsys.readouterr().err
    assert main(["--config", str(config), "show", "rotate"]) == 0


def test_a_config_error_names_the_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("theme = 1\n")
    assert main(["--config", str(path), "list"]) == 2
    assert capsys.readouterr().err == f"pixdial: {path}: theme: must be text, not 1\n"


def test_render_writes_pngs(config: Path, tmp_path: Path) -> None:
    args = ["--config", str(config), "render", "crown:ice", "minimal", "--state", "full", "--out", str(tmp_path)]
    assert main(args) == 0
    assert Image.open(tmp_path / "crown-ice-full@1x.png").size == (400, 400)
    assert (tmp_path / "minimal-full@1x.png").exists()
    assert main(["--config", str(config), "render", "nope"]) == 2


def test_list_and_doctor(config: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", str(config), "list"]) == 0
    assert "crown " in capsys.readouterr().out
    assert main(["--config", str(config), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "ok    panel top" in out and "FAIL" not in out


@pytest.fixture
def stopped(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`run` gets a SIGTERM after half a second; its log setup is undone after the test."""
    handlers: dict[int, Callable[[], None]] = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    timer = threading.Timer(0.5, lambda: handlers[signal.SIGTERM]())
    timer.start()
    log = logging.getLogger("pixdial")
    kept, level = list(log.handlers), log.level
    yield
    timer.cancel()
    for handler in log.handlers[len(kept) :]:
        handler.close()
    log.handlers[:] = kept
    log.setLevel(level)


def test_run_logs_its_panels_and_sources_then_what_breaks_or_works(
    config: Path, capsys: pytest.CaptureFixture[str], stopped: None
) -> None:
    assert main(["--config", str(config), "run"]) == 0
    first, *rest = capsys.readouterr().out.splitlines()
    assert first == f"pixdial {__version__}: panels top (Png), 2 (Png); sources none"
    assert set(rest) == {
        "layout: working, designs crown gpu",
        f"top panel: working, info writing {config.parent / 'a.png'}",
        f"2 panel: working, info writing {config.parent / 'b.png'}",
    }


def test_run_debug_logs_to_a_file_with_the_time_level_thread_and_tracebacks(config: Path, stopped: None) -> None:
    (config.parent / "a.png").mkdir()  # where the top panel's frames go: it can't replace a folder with one
    path = config.parent / "run.log"
    assert main(["--config", str(config), "run", "--debug", "--log-file", str(path)]) == 0
    text = path.read_text()
    assert re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} INFO \[MainThread\] pixdial ", text)
    assert "WARNING [panel top] top panel: [Errno 21] Is a directory" in text
    assert "Traceback (most recent call last)" in text and "IsADirectoryError" in text
    assert "DEBUG [panel top] next try in 0.2 s" in text


def test_run_says_when_it_cannot_write_its_log_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--log-file", str(tmp_path / "no" / "run.log")]) == 2
    assert "No such file or directory" in capsys.readouterr().err
