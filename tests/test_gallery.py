"""Gallery files, animation timing and local HTML links, without hardware."""

from __future__ import annotations

from collections.abc import Hashable
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image, ImageChops, PngImagePlugin

from pixdial import cli
from pixdial import config as cfg
from pixdial.designs import THEMES, Design
from pixdial.designs.cpu import Minimal, Orb
from pixdial.gallery import WARM_UP, Demo
from pixdial.readings import Snapshot
from pixdial.runtime import Catalog


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if (tag, key) in (("img", "src"), ("a", "href")) and value is not None:
                self.paths.append(value)


def test_gallery_writes_pngs_animation_sheets_and_working_html_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = Catalog({"minimal": Minimal, "orb": Orb}, THEMES, "warm")
    monkeypatch.setattr(cfg, "catalog", lambda config: catalog)
    monkeypatch.setattr(Minimal, "about", '<temperature> & "load"')
    monkeypatch.setattr(Minimal, "shows", "CPU <load> & temperature")
    config = tmp_path / "config.toml"
    config.write_text("sources = []\n")
    out = tmp_path / "gallery with spaces"
    assert cli.main(["--config", str(config), "render", "--gallery", str(out)]) == 0
    assert capsys.readouterr().out.splitlines() == ["minimal: 4 images", "orb: 5 images", str(out / "gallery.html")]
    expected = {
        f"{name}-{state}@{scale}x.png" for name in ("minimal", "orb") for state in ("busy", "idle") for scale in (1, 2)
    }
    expected |= {f"{name}-{theme}@2x.png" for name in ("minimal", "orb") for theme in THEMES}
    expected |= {"orb-busy-anim.png", "sheet-1.png", "sheet-2.png", "gallery.html"}
    assert {p.name for p in out.iterdir()} == expected
    for name in expected - {"gallery.html"}:
        with Image.open(out / name) as image:
            assert image.format == "PNG"
            image.verify()
        with Image.open(out / name) as image:
            if name.startswith("sheet-"):
                assert image.size == (1760, 1960)
                assert image.getpixel((40, 40)) == (24, 24, 28)  # outside the circular panel mask
            else:
                size = 800 if "@2x" in name else 400
                assert image.size == (size, size)
    with Image.open(out / "orb-busy-anim.png") as animation:
        assert isinstance(animation, PngImagePlugin.PngImageFile)
        assert animation.n_frames == 30
        assert animation.info["loop"] == 0
        assert animation.info["duration"] == pytest.approx(66)
        first = animation.convert("RGB")
        animation.seek(1)
        assert ImageChops.difference(first, animation.convert("RGB")).getbbox() is not None
    page = (out / "gallery.html").read_text()
    assert "&lt;temperature&gt; &amp; &quot;load&quot;" in page
    assert "CPU &lt;load&gt; &amp; temperature" in page
    assert "<temperature>" not in page
    links = Links()
    links.feed(page)
    assert len(links.paths) == 17
    assert all((out / path).is_file() for path in links.paths)
    assert {"sheet-1.png", "sheet-2.png", "orb-busy-anim.png"} <= set(links.paths)


class Recorded(Design):
    name = "recorded"
    shows = "Time"

    def __init__(self) -> None:
        super().__init__(THEMES["warm"])
        self.updates: list[tuple[float, float]] = []
        self.renders: list[float] = []

    def update(self, r: Snapshot, now: float, dt: float) -> tuple[Hashable, Hashable | None]:
        self.updates.append((now, dt))
        return now, None

    def render(self, now: float) -> Image.Image:
        self.renders.append(now)
        return Image.new("RGB", (1, 1))


@pytest.mark.parametrize(("fps", "count"), [(0, 0), (10, 20), (20, 40), (30, 40)])
def test_demo_warms_up_and_caps_the_animation_at_forty_frames(
    fps: int, count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Recorded, "fps", fps)
    design = Recorded()
    demo = Demo(design, "busy", {})
    assert len(design.updates) == 260
    assert design.updates[0] == (0, 0.5)
    assert design.updates[-1] == (129.5, 0.5)
    assert demo.render().size == (1, 1)
    frames = demo.frames()
    try:
        assert len(frames) == count
        expected = [WARM_UP + i / fps for i in range(count)]
        assert design.renders == [WARM_UP, *expected]
        assert design.updates[260:] == [(now, 1 / fps) for now in expected]
    finally:
        for frame in frames:
            frame.close()
