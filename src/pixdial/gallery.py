"""Rendering designs without hardware: one picture, an animation, or the whole gallery with its web page."""

from __future__ import annotations

import html
import textwrap
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import NAME, demo
from .designs import Design
from .designs.geometry import FONTS
from .readings import Meta
from .runtime import Catalog, Feed

WARM_UP = 130.0  # s of demo readings a design is fed first, so its history, trails and easing look live


class Demo:
    """A design fed a demo state's readings every half second, as if it had been running."""

    def __init__(self, design: Design, state: str, meta: Mapping[str, Meta]) -> None:
        self.design, self.state = design, state
        self.feed = Feed(meta, type(design).trails)
        for t in np.arange(0, WARM_UP, 0.5):
            self.step(float(t), 0.5)

    def step(self, t: float, dt: float) -> None:
        snapshot = self.feed.snapshot(demo.readings(self.state, t), t, demo.START + t)
        self.design.update(snapshot, t, dt)

    def render(self) -> Image.Image:
        return self.design.render(WARM_UP)

    def frames(self) -> list[Image.Image]:
        """Two seconds of its animation (at most 40 frames)."""
        fps = self.design.fps
        frames = []
        for i in range(min(fps * 2, 40)):
            now = WARM_UP + i / fps
            self.step(now, 1 / fps)
            frames.append(self.design.render(now))
        return frames


def gallery(out: Path, catalog: Catalog, meta: Mapping[str, Meta], log: Callable[[str], None] = print) -> None:
    """Every design at 400 and 800 px in its preview states, the animated ones as APNG, three designs in every
    theme, contact sheets of four, and gallery.html."""
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, cls in catalog.designs.items():
        files: dict[tuple[str, int] | str, str] = {}
        for state in cls.previews:
            for scale in (1, 2):
                path = f"{name}-{state}@{scale}x.png"
                Demo(catalog.make(name, scale), state, meta).render().save(out / path)
                files[state, scale] = path
        if cls.fps:
            frames = Demo(catalog.make(name), "busy", meta).frames()
            path = f"{name}-busy-anim.png"
            frames[0].save(out / path, save_all=True, append_images=frames[1:], duration=1000 // cls.fps, loop=0)
            files["anim"] = path
        entries.append((cls, files))
        log(f"{name}: {len(files)} images")
    themes = []
    for name in list(catalog.designs)[:3]:
        for theme in catalog.themes:
            path = f"{name}-{theme}@2x.png"
            Demo(catalog.make(f"{name}:{theme}", 2), "busy", meta).render().save(out / path)
            themes.append((f"{name}:{theme}", path))
    sheets = contact_sheets(out, entries, themes)
    write_html(out, entries, themes, sheets)


Entries = list[tuple[type[Design], dict[tuple[str, int] | str, str]]]


def contact_sheets(out: Path, entries: Entries, themes: list[tuple[str, str]]) -> list[str]:
    font = ImageFont.truetype(str(FONTS / "Lato-Bold.ttf"), 34)
    small = ImageFont.truetype(str(FONTS / "Lato-Regular.ttf"), 24)
    circle = Image.new("L", (800, 800))
    ImageDraw.Draw(circle).ellipse((0, 0, 799, 799), fill=255)
    cells = [(cls.name, cls.shows, files["busy", 2]) for cls, files in entries]
    cells += [(spec, "theme " + spec.split(":")[1], path) for spec, path in themes]
    sheets = []
    for n in range(0, len(cells), 4):
        sheet = Image.new("RGB", (2 * 860 + 40, 2 * 960 + 40), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)
        for i, (name, shows, path) in enumerate(cells[n : n + 4]):
            x, y = 40 + (i % 2) * 860, 40 + (i // 2) * 960
            sheet.paste(Image.open(out / path), (x, y), circle)
            draw.text((x, y + 820), name, font=font, fill=(255, 236, 214))
            for j, line in enumerate(textwrap.wrap(shows, 62)[:2]):
                draw.text((x, y + 866 + 30 * j), line, font=small, fill=(150, 140, 130))
        path = f"sheet-{n // 4 + 1}.png"
        sheet.save(out / path)
        sheets.append(path)
    return sheets


def write_html(out: Path, entries: Entries, themes: list[tuple[str, str]], sheets: list[str]) -> None:
    def img(path: str, size: int = 400) -> str:
        return f'<img src="{html.escape(path)}" width="{size}" height="{size}" loading="lazy">'

    cards = []
    for cls, files in entries:
        shots = [img(files[state, 2]) for state in cls.previews]
        if "anim" in files:
            shots.append(img(files["anim"]))
        animated = f" &middot; animated, {cls.fps} frames/s" if cls.fps else ""
        cards.append(f"""<section><h2>{cls.name}</h2><p>{html.escape(cls.about)}</p>
<p class="shows">Shows: {html.escape(cls.shows)}{animated}</p>
<div class="shots">{"".join(shots)}</div>
<p class="sizes">Native: <a href="{files["busy", 1]}">400 px</a> &middot; <a href="{files["busy", 2]}">800 px</a></p>
</section>""")
    theme_cells = "".join(
        f"<figure>{img(path, 300)}<figcaption>{html.escape(spec)}</figcaption></figure>" for spec, path in themes
    )
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{NAME} designs</title>
<style>
body {{ background: #141417; color: #ece0d4; margin: 40px;
       font: 16px/1.5 -apple-system, "Helvetica Neue", sans-serif; }}
h1 {{ font-weight: 800; }} h2 {{ margin: 0 0 4px; font-size: 26px; }}
section {{ background: #1c1c21; border-radius: 16px; padding: 24px; margin: 0 0 28px; }}
.shots img, figure img {{ border-radius: 50%; margin: 10px 14px 0 0; background: #000; }}
.shows, .sizes, figcaption {{ color: #9d9186; margin: 4px 0; }} a {{ color: #ffb37a; }}
code {{ background: #2a2a31; padding: 2px 6px; border-radius: 6px; }}
figure {{ display: inline-block; margin: 0 8px 12px 0; text-align: center; }}
</style></head><body>
<h1>{NAME} designs</h1>
<p>Each design fills one round 400&times;400 LCD. Pick one per panel, in the config's order, with an optional theme
(<code>warm</code>: warm white, green, orange, red; <code>ember</code>; <code>ice</code>):</p>
<p><code>{NAME} show crown gpu psu</code> &nbsp; (e.g. <code>{NAME} show clock pins quota:ember</code>), or
<code>{NAME} show rotate</code> for every design in turn. A running <code>{NAME} run</code> switches within a second,
fading the new design in; <code>{NAME} list</code> lists the designs.</p>
<p>Contact sheets: {" ".join(f'<a href="{s}">{s}</a>' for s in sheets)}</p>
{"".join(cards)}
<section><h2>themes</h2><p>Three designs in each theme.</p>{theme_cells}</section>
</body></html>"""
    (out / "gallery.html").write_text(page)
