"""The command line: what it prints and its exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageFont

from pixdial.cli import main
from pixdial.devices import Found, Slv3

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
    assert capsys.readouterr().out == "clock clock\n"  # with no sources, only the clock has what it shows
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
    assert "the default rotation leaves out crown, gpu, psu," in out  # sources = []: only the clock is left


def test_list_and_devices_mark_a_tl_lcd_experimental(
    config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    found = [Found("SLV3SERIAL", "usb 1-2", True), Found("TLSERIAL", "usb 1-3", False, "TL Wireless LCD, experimental")]
    monkeypatch.setattr(Slv3, "discover", classmethod(lambda cls: found))
    assert main(["--config", str(config), "devices"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "slv3  SLV3SERIAL  usb 1-2  ok  not in the config",
        "slv3  TLSERIAL  usb 1-3  no access (`pixdial setup` gives it)  not in the config"
        "  (TL Wireless LCD, experimental)",
    ]
    assert main(["--config", str(config), "list"]) == 0
    assert "devices: slv3 (SL V3 Wireless LCD 1cbe:0005; TL Wireless LCD 1cbe:0006, experimental), png\n" in (
        capsys.readouterr().out
    )


def test_doctor_says_whether_pillow_has_raqm(
    config: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["--config", str(config), "doctor"]) == 0
    assert "ok    raqm             yes" in capsys.readouterr().out
    monkeypatch.setattr(ImageFont.core, "HAVE_RAQM", False)
    assert main(["--config", str(config), "doctor"]) == 0
    assert "skip  raqm             no\n      Text is set without the font's kerning" in capsys.readouterr().out
