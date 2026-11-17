"""A panel's own picture under its design: checked before it is decoded, cover-fitted with a dark edge, capped in
memory, composed under every design the same way still or animated, at the right rate, from the config."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import PIL
import pytest
from PIL import Image

from pixdial import config as cfg
from pixdial import doctor
from pixdial.designs import BUILTIN, THEMES, Design, Still
from pixdial.gallery import WARM_UP, Demo
from pixdial.runtime import Catalog, Layout, Report
from pixdial.runtime import backdrop as bd
from pixdial.runtime.backdrop import Backdrop, BackdropError
from pixdial.runtime.screen import compose, draw
from tests import logged
from tests.test_runtime import Rig

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def gif(path: Path, colours: list[tuple[int, int, int]], ms: int, size: tuple[int, int] = (64, 64)) -> Path:
    frames = [Image.new("RGB", size, c) for c in colours]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, disposal=1)
    return path


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def apng_header(path: Path, width: int, height: int, frames: int) -> Path:
    """An APNG whose header claims this canvas and frame count, with almost no pixel data behind it."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    actl = struct.pack(">II", frames, 0)
    body = chunk(b"IHDR", ihdr) + chunk(b"acTL", actl) + chunk(b"IDAT", zlib.compress(b"\0" * 64)) + chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + body)
    return path


# ---------------------------------------------------------------- the file


def test_a_pillow_older_than_13_is_refused_with_one_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.png"
    Image.new("RGB", (8, 8)).save(path)
    monkeypatch.setattr(PIL, "__version__", "12.2.0")
    with pytest.raises(BackdropError, match=r"needs Pillow 13\.0\.0 or newer .* this is Pillow 12\.2\.0"):
        Backdrop(path)


def test_only_png_jpeg_gif_and_webp_open(tmp_path: Path) -> None:
    for fmt in ("PNG", "JPEG", "GIF", "WEBP"):
        Image.new("RGB", (8, 8)).save(tmp_path / f"a.{fmt}", fmt)
        Backdrop(tmp_path / f"a.{fmt}")
    Image.new("RGB", (8, 8)).save(tmp_path / "a.bmp")  # Pillow opens it, a backdrop does not
    with pytest.raises(BackdropError, match="not a PNG, JPEG, GIF or WebP picture"):
        Backdrop(tmp_path / "a.bmp")
    with pytest.raises(BackdropError, match="no such file"):
        Backdrop(tmp_path / "gone.png")


@pytest.mark.parametrize(("width", "height", "frames"), [(5000, 5000, 2), (20000, 20000, 2), (64, 64, 200_000)])
def test_a_large_canvas_or_frame_count_is_refused_from_the_header(
    tmp_path: Path, width: int, height: int, frames: int
) -> None:
    """An APNG that claims a 25 or 400 megapixel canvas, or 200,000 frames: refused before a pixel is decoded (the
    file holds none to decode)."""
    with pytest.raises(BackdropError, match="a backdrop has at most 16,777,216 pixels"):
        Backdrop(apng_header(tmp_path / "big.png", width, height, frames))


def test_a_photo_is_cover_fitted_at_the_size_asked_for(tmp_path: Path) -> None:
    wide = Image.new("RGB", (900, 300), RED)
    wide.paste(GREEN, (300, 0, 600, 300))
    wide.paste(BLUE, (600, 0, 900, 300))
    wide.save(tmp_path / "wide.png")
    backdrop = Backdrop(tmp_path / "wide.png")
    for size in (200, 400, 800):  # the canvas the design gets, not a fixed 400
        (frame,) = backdrop.at(size).frames
        assert frame.shape == (size, size, 3)
        assert frame[size // 2, size // 2, 1] > 150  # green fills the middle; the red and blue sides are cut off
        assert frame[:, :, 0].max() < 30 and frame[:, :, 2].max() < 30  # what resampling rings in at the cut


def test_a_photo_is_darker_towards_the_panel_s_edge(tmp_path: Path) -> None:
    Image.new("RGB", (100, 100), (200, 200, 200)).save(tmp_path / "grey.png")
    (frame,) = Backdrop(tmp_path / "grey.png").at(400).frames
    across = frame[200, 200:, 0].astype(int)
    assert across[0] == int(200 * bd.MIDDLE)
    assert across[-1] == int(200 * bd.EDGE)
    assert (np.diff(across) <= 0).all()


def test_a_transparent_picture_goes_over_black(tmp_path: Path) -> None:
    Image.new("RGBA", (8, 8), (255, 255, 255, 0)).save(tmp_path / "clear.png")
    (frame,) = Backdrop(tmp_path / "clear.png").at(40).frames
    assert frame.max() == 0


def test_a_gif_s_frames_keep_their_times(tmp_path: Path) -> None:
    pictures = Backdrop(gif(tmp_path / "a.gif", [RED, GREEN, BLUE], 50)).at(40)
    assert pictures.animated and pictures.fps == pytest.approx(20)
    assert pictures.ends == pytest.approx([0.05, 0.1, 0.15])
    assert [pictures.index(t) for t in (0.0, 0.049, 0.051, 0.12, 0.151, 1.06)] == [0, 0, 1, 2, 0, 0]
    assert [int(np.argmax(f[20, 20])) for f in pictures.frames] == [0, 1, 2]


def test_a_gif_frame_without_a_time_shows_for_a_tenth_of_a_second(tmp_path: Path) -> None:
    pictures = Backdrop(gif(tmp_path / "a.gif", [RED, GREEN], 0)).at(40)
    assert pictures.ends == pytest.approx([0.1, 0.2])


def test_a_many_frame_gif_keeps_the_first_frames_that_fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = gif(tmp_path / "long.gif", [(i % 256, 0, 0) for i in range(400)], 40)
    decoded, fit = [], bd.fit

    def counted(image: Image.Image, size: int) -> bd.Frame8:
        decoded.append(image.tell())
        return fit(image, size)

    monkeypatch.setattr(bd, "fit", counted)
    pictures = Backdrop(path).at(400)
    kept = bd.MEMORY // (400 * 400 * 3)
    assert kept == 133
    assert len(pictures.frames) == kept and pictures.total == 400
    assert decoded == list(range(kept))  # the frames after them are never decoded
    assert sum(f.nbytes for f in pictures.frames) <= bd.MEMORY


def test_a_large_canvas_apng_decodes_only_what_the_decode_budget_allows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames = [Image.new("RGB", (2048, 1024), c) for c in (RED, GREEN, BLUE, RED, GREEN, BLUE)]
    frames[0].save(tmp_path / "big.png", save_all=True, append_images=frames[1:], duration=100)
    monkeypatch.setattr(bd, "DECODE", 4 * 2048 * 1024)
    pictures = Backdrop(tmp_path / "big.png").at(400)
    assert (len(pictures.frames), pictures.total) == (4, 6)
    assert [int(np.argmax(f[200, 200])) for f in pictures.frames] == [0, 1, 2, 0]


# ---------------------------------------------------------------- under a design


@pytest.mark.parametrize("name", BUILTIN)
def test_an_animated_backdrop_s_frame_is_the_same_as_that_picture_still(name: str, tmp_path: Path) -> None:
    """Each frame of an animation is composed under the cached still part (with the text folded in where the moving
    part keeps clear of it); a still picture goes into the still part. Both give the same frame."""
    animated = Backdrop(gif(tmp_path / "a.gif", [(250, 180, 40), (40, 90, 250)], 100, (300, 200))).at(400)
    for picture in animated.frames:
        design = Demo(BUILTIN[name](THEMES["warm"]), "busy", {}).design
        still = bd.Pictures((picture,), np.array([0.1]), 1)
        one = compose(design, draw(design, still), WARM_UP, picture).astype(int)
        each = compose(design, draw(design, animated), WARM_UP, picture).astype(int)
        assert np.abs(one - each).max() <= 1
        plain = compose(design, draw(design, None), WARM_UP, None).astype(int)
        assert np.abs(one - plain).max() > 50  # the picture shows


class Old(Design):
    """A plugin design from before the still part said where its background shows."""

    name, shows = "old", "a grey panel"

    def update(self, r: object, now: float, dt: float) -> tuple[int, None]:
        return 0, None

    def still(self) -> Still:
        return np.full((400, 400, 3), 60, np.float32), []  # type: ignore[return-value]


def test_a_design_that_does_not_say_where_its_background_shows_hides_the_backdrop(tmp_path: Path) -> None:
    design = Old(THEMES["warm"])
    pictures = Backdrop(gif(tmp_path / "a.gif", [RED, GREEN], 100)).at(400)
    assert (compose(design, draw(design, pictures), 0.0, pictures.frames[0]) == 60).all()


def backdrop_rig(tmp_path: Path, designs: tuple[str, ...], picture: Path, max_fps: float = 30) -> Rig:
    rig = Rig(tmp_path, designs, max_fps=max_fps)
    for screen in rig.runner.screens:
        screen.backdrop = Backdrop(picture)
    return rig


def test_a_still_backdrop_goes_in_the_still_part(tmp_path: Path) -> None:
    Image.new("RGB", (64, 64), RED).save(tmp_path / "red.png")
    rig = backdrop_rig(tmp_path, ("minimal",), tmp_path / "red.png")
    rig.set(cpu_c=40)
    rig.run_for(65)
    sent = [t - 1000 for t, _ in rig.panels[0].frames]
    assert sent == pytest.approx([0, 30, 60], abs=0.11)  # once, then every 30 s, as without one
    red, green, blue = np.asarray(rig.panels[0].frames[0][1]).reshape(-1, 3).mean(axis=0)
    assert red > green + 60 and red > blue + 60  # the picture shows round the reading


@pytest.mark.parametrize(("design", "max_fps", "fps"), [("minimal", 30, 20), ("minimal", 10, 10), ("orb", 30, 15)])
def test_a_gif_plays_at_its_own_rate_at_most_the_design_s(
    tmp_path: Path, design: str, max_fps: float, fps: int
) -> None:
    """A 20 fps GIF under a still design plays at 20 frames a second, under max_fps 10 at 10, under orb (a 15 fps
    design) at 15; each frame that goes out shows the GIF's frame for its time."""
    picture = gif(tmp_path / "a.gif", [RED, GREEN, BLUE, (255, 255, 0)], 50, (400, 400))
    rig = backdrop_rig(tmp_path, (design,), picture, max_fps)
    rig.set(cpu_c=40, cpu_load=30)
    rig.run_for(1)
    start = rig.clock.now
    rig.run_for(2)
    sent = [(t, np.asarray(im)) for t, im in rig.panels[0].frames if t >= start]
    assert len(sent) == pytest.approx(2 * fps, abs=1)
    pictures = rig.runner.screens[0].pictures
    assert pictures is not None
    for t, frame in sent:
        expected = int(np.argmax(pictures.frames[pictures.index(t)][200, 6]))  # outside every design's rings
        assert int(np.argmax(frame[200, 6])) == expected


def test_a_backdrop_that_fails_to_decode_is_reported_and_the_design_shows(tmp_path: Path) -> None:
    path = gif(tmp_path / "a.gif", [RED, GREEN], 100)
    rig = backdrop_rig(tmp_path, ("minimal",), path)
    path.write_bytes(path.read_bytes()[:40])  # cut short after it was checked
    rig.set(cpu_c=40)
    rig.run_for(1)
    assert rig.panels[0].frames
    assert any(line.startswith("0 backdrop: ") for line in rig.lines)


def test_a_backdrop_that_keeps_only_its_first_frames_says_so(tmp_path: Path) -> None:
    path = gif(tmp_path / "long.gif", [(i % 256, 0, 0) for i in range(150)], 40, (8, 8))
    rig = backdrop_rig(tmp_path, ("minimal",), path)
    rig.set(cpu_c=40)
    rig.run_for(0.5)
    assert (
        "0 backdrop: the first 133 of its 150 frames play; a backdrop keeps 64 MB of frames and decodes 512 Mpx at most"
        in rig.lines
    )


def test_none_shows_the_backdrop_alone(tmp_path: Path) -> None:
    Image.new("RGB", (64, 64), (200, 200, 200)).save(tmp_path / "grey.png")
    rig = backdrop_rig(tmp_path, ("none",), tmp_path / "grey.png")
    rig.set()
    rig.run_for(0.5)
    frame = np.asarray(rig.panels[0].frames[0][1])
    (picture,) = Backdrop(tmp_path / "grey.png").at(400).frames
    assert np.abs(frame.astype(int) - picture).max() <= 1


def test_none_is_not_in_the_default_rotation(tmp_path: Path) -> None:
    catalog = Catalog(BUILTIN, THEMES, "warm")
    catalog.check("none")
    assert "none" not in catalog.designs
    Layout(catalog, 2, tmp_path / "layout", ("none", "crown:ice"), list(catalog.designs), 60)


# ---------------------------------------------------------------- the config


def test_the_config_names_a_panel_s_backdrop_from_its_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    Image.new("RGB", (8, 8), RED).save(tmp_path / "red.png")
    config = cfg.parse(
        {
            "layout": ["minimal", "none", "crown"],
            "sources": [],
            "panels": [
                {"device": "png", "path": str(tmp_path / "1.png"), "backdrop": "red.png"},
                {"device": "png", "path": str(tmp_path / "2.png"), "backdrop": str(tmp_path / "red.png")},
                {"device": "png", "path": str(tmp_path / "3.png")},
            ],
        },
        tmp_path / "config.toml",
    )
    assert [e.backdrop for e in config.panels] == [tmp_path / "red.png", tmp_path / "red.png", None]
    assert all("backdrop" not in e.options for e in config.panels)  # not for the device
    first, second, third = cfg.backdrops(config)
    assert first is second and third is None  # one file, decoded once
    screens = cfg.runner(config, Report(logged([]))).screens
    assert screens[0].backdrop is screens[1].backdrop is not None and screens[2].backdrop is None


def test_a_panel_s_bad_backdrop_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a picture")
    config = cfg.parse({"panels": [{"device": "png", "path": "a.png"}, {"backdrop": "notes.txt"}]}, tmp_path / "c.toml")
    with pytest.raises(cfg.ConfigError, match=r"panels\[1\]\.backdrop: .*notes\.txt: not a PNG, JPEG, GIF or WebP"):
        cfg.backdrops(config)
    with pytest.raises(cfg.ConfigError, match=r"panels\[0\]\.backdrop: must be text"):
        cfg.parse({"panels": [{"backdrop": 3}]}, tmp_path / "c.toml")


def test_doctor_checks_each_backdrop(tmp_path: Path) -> None:
    Image.new("RGB", (8, 8)).save(tmp_path / "ok.png")
    (tmp_path / "notes.txt").write_text("not a picture")
    for name, status in (("ok.png", doctor.OK), ("notes.txt", doctor.FAIL)):
        config = cfg.parse({"panels": [{"device": "png", "path": "a.png", "backdrop": name}]}, tmp_path / "c.toml")
        (check,) = [c for c in doctor.panels(config) if c.what == "backdrops"]
        assert check.status == status and name in check.detail
