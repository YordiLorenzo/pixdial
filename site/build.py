"""Rebuild the website's WebP images from real CLI renders and docs/images.

Run from a source checkout with ``uv run python site/build.py``. Intermediate
PNGs stay in build/site. Fonts and fitted favicons are committed brand assets.
No physical device or user configuration is opened.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from pixdial.designs import BUILTIN, THEMES

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
IMAGES = SITE / "images"
WORK = ROOT / "build" / "site"
WIDTHS = (400, 640, 960, 1280)


def webp(source: Path, stem: str, widths: tuple[int, ...] = WIDTHS) -> None:
    with Image.open(source) as original:
        for width in widths:
            if width > original.width:
                raise ValueError(f"Refusing to upscale {source.name} to {width}px")
            height = round(original.height * width / original.width)
            resized = original.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
            resized.save(IMAGES / f"{stem}-{width}.webp", quality=82, method=6)


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    config = WORK / "config.toml"
    config.write_text('theme = "warm"\nsources = []\n', encoding="utf-8")
    specs = [*BUILTIN, *(f"crown:{theme}" for theme in THEMES if theme != "warm")]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pixdial",
            "--config",
            str(config),
            "render",
            *specs,
            "--state",
            "busy",
            "--scale",
            "4",
            "--out",
            str(WORK / "renders"),
        ],
        cwd=ROOT,
        check=True,
        timeout=300,
    )
    for spec in specs:
        stem = spec.replace(":", "-")
        widths = (*WIDTHS, 1600) if spec == "crown" else WIDTHS
        webp(WORK / "renders" / f"{stem}-busy@4x.png", stem, widths)
    for name in ("logo.svg", "icon.svg", "social-preview.png"):
        shutil.copyfile(ROOT / "docs" / "images" / name, IMAGES / name)

    # The same catalog drives the hero rotation and the visible, static gallery.
    (SITE / "designs.json").write_text(
        json.dumps([{"name": name, "alt": cls.shows} for name, cls in BUILTIN.items()], indent=2) + "\n",
        encoding="utf-8",
    )
    published = [p for p in SITE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    total = sum(p.stat().st_size for p in published)
    if total > 4_000_000:
        raise ValueError(f"Site is {total:,} bytes; keep the complete site under 4 MB")
    print(f"Website: {len(specs)} real renders; {len(published)} files; {total:,} bytes")


if __name__ == "__main__":
    main()
