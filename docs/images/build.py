"""Rebuild the README graphics from CLI renders: uv run python docs/images/build.py.

The source PNGs and APNG animation are produced by `uv run pixdial render`.
Pillow only resizes, masks the round panels, adds labels and encodes the WebP.
Intermediate output stays under build/readme/; no panel is opened.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence

from pixdial.designs import BUILTIN, THEMES
from pixdial.designs.geometry import FONTS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "images"
WORK = ROOT / "build" / "readme"
GROUND = "#070402"
TEXT = "#FFF4E6"
MAX_BYTES = 1_500_000


def render(*args: str) -> None:
    subprocess.run(
        ["uv", "run", "pixdial", "--config", str(WORK / "config.toml"), "render", *args],
        cwd=ROOT,
        check=True,
        timeout=300,
        capture_output=True,
        text=True,
    )


def circle(image: Image.Image, size: int) -> Image.Image:
    mask = Image.new("L", (size * 4, size * 4))
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    panel = image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    panel.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    return panel


def sheet(entries: list[tuple[str, Path]], columns: int, size: int) -> Image.Image:
    margin, gap, label_height = 48, 32, 68
    rows = (len(entries) + columns - 1) // columns
    width = 2 * margin + columns * size + (columns - 1) * gap
    height = 2 * margin + rows * (size + label_height) + (rows - 1) * 16
    canvas = Image.new("RGB", (width, height), GROUND)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(FONTS / "Lato-Regular.ttf"), 28)
    for index, (label, source) in enumerate(entries):
        row, col = divmod(index, columns)
        count = min(columns, len(entries) - row * columns)
        row_width = count * size + (count - 1) * gap
        x = (width - row_width) // 2 + col * (size + gap)
        y = margin + row * (size + label_height + 16)
        with Image.open(source) as original:
            panel = circle(original, size)
            canvas.paste(panel, (x, y), panel)
        draw.text((x + size / 2, y + size + 28), label, font=font, fill=TEXT, anchor="mm")
    return canvas


def animation(source: Path, destination: Path) -> None:
    frames, durations = [], []
    with Image.open(source) as original:
        for frame in ImageSequence.Iterator(original):
            canvas = Image.new("RGB", (480, 480), GROUND)
            panel = circle(frame, 400)
            canvas.paste(panel, (40, 40), panel)
            frames.append(canvas)
            durations.append(round(frame.info["duration"]))
    frames[0].save(
        destination,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        lossless=True,
        method=6,
    )


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "config.toml").write_text('theme = "warm"\nsources = []\n')
    renders = WORK / "renders"
    render(*BUILTIN, "--scale", "2", "--out", str(renders))
    render(*(f"crown:{theme}" for theme in THEMES), "--scale", "2", "--out", str(renders))
    sheet([(name, renders / f"{name}-busy@2x.png") for name in BUILTIN], 4, 300).save(
        OUT / "designs.png", optimize=True
    )
    sheet([(theme, renders / f"crown-{theme}-busy@2x.png") for theme in THEMES], 3, 400).save(
        OUT / "themes.png", optimize=True
    )
    render("--gallery", str(WORK / "gallery"))
    animation(WORK / "gallery" / "orb-busy-anim.png", OUT / "demo.webp")
    for name in ("designs.png", "themes.png", "demo.webp"):
        size = (OUT / name).stat().st_size
        if size >= MAX_BYTES:
            raise ValueError(f"{name}: {size:,} bytes exceeds the README image budget")
        print(f"docs/images/{name}: {size:,} bytes")


if __name__ == "__main__":
    main()
