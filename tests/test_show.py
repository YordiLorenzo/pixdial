"""Changing or inspecting a layout saved by an older config or plugin set."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial import config as cfg
from pixdial.cli import main


@pytest.fixture
def saved_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "saved state"))
    path = tmp_path / "config.toml"
    path.write_text(
        "sources = []\n"
        f'[[panels]]\ndevice = "png"\npath = "{tmp_path / "top panel.png"}"\n'
        f'[[panels]]\ndevice = "png"\npath = "{tmp_path / "bottom panel.png"}"\n'
    )
    state = cfg.state_path()
    state.parent.mkdir(parents=True)
    return path, state


@pytest.mark.parametrize(
    ("stale", "reason"),
    [
        ("removed clock\n", "no design 'removed'"),
        ("clock:removed clock\n", "no theme 'removed'"),
        ("clock\n", "1 designs for 2 panels"),
        ("", "0 designs for 2 panels"),
    ],
)
def test_show_reports_a_stale_layout_without_rewriting_it(
    saved_layout: tuple[Path, Path], capsys: pytest.CaptureFixture[str], stale: str, reason: str
) -> None:
    config, state = saved_layout
    state.write_text(stale)
    assert main(["--config", str(config), "show"]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert "saved layout" in out.err and reason in out.err
    assert "pixdial show" in out.err
    assert state.read_text() == stale


def test_show_rejects_a_bad_replacement_even_when_the_saved_layout_is_stale(
    saved_layout: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, state = saved_layout
    state.write_text("removed clock\n")
    assert main(["--config", str(config), "show", "clock"]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert "saved layout" in out.err
    assert state.read_text() == "removed clock\n"


@pytest.mark.parametrize("specs", [["clock:ice", "orb"], ["rotate"]])
def test_show_can_replace_a_stale_saved_layout(
    saved_layout: tuple[Path, Path], capsys: pytest.CaptureFixture[str], specs: list[str]
) -> None:
    config, state = saved_layout
    state.write_text("removed clock\n")
    assert main(["--config", str(config), "show", *specs]) == 0
    out = capsys.readouterr()
    expected = " ".join(specs) + "\n"
    assert out.out == expected and out.err == ""
    assert state.read_text() == expected
    assert main(["--config", str(config), "show"]) == 0
    assert capsys.readouterr().out == expected
