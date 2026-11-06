"""Drawing a frame: shapes that light their own glow, text that fits inside the round panel, big numbers."""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter

from .colour import Theme
from .geometry import F32, MID, Kit, Ring, inside

DASH, DOT = "—", "  ·  "  # a missing reading; between two readings on a line

Pixels = NDArray[Any]  # a float picture being drawn, or a finished 8-bit one (moving parts paint on either)
Region = tuple[slice, slice]
TextLayer = tuple[tuple[int, int, int], Region, NDArray[Any]]  # a colour, the box its text covers, the coverage there
Still = tuple[F32, list[TextLayer]]


def paint(px: Pixels, ring: Ring, alpha: F32, colour: Sequence[float] | F32) -> None:
    """Blend colour (one RGB, or one per ring pixel) over px by alpha, only where alpha is above zero."""
    on = alpha > 0
    idx, a = ring.idx[on], alpha[on, None]
    c = colour[on] if np.ndim(colour) == 2 else np.asarray(colour, np.float32)  # type: ignore[call-overload]
    flat = px.reshape(-1, 3)
    flat[idx] = flat[idx] + (c - flat[idx]) * a


def add(px: Pixels, sl: Any, light: Pixels) -> None:
    """Light added to px[sl], kept within 8 bits."""
    px[sl] = np.minimum(px[sl] + light, 255)


def disc(px: Pixels, kit: Kit, x: float, y: float, r: float, colour: Sequence[float], alpha: float = 1.0) -> None:
    """An antialiased disc at (x, y) with radius r."""
    s = kit.s
    cx, cy, rr = x * s, y * s, r * s
    x0, x1 = max(0, int(cx - rr - 2)), min(kit.size, int(cx + rr + 3))
    y0, y1 = max(0, int(cy - rr - 2)), min(kit.size, int(cy + rr + 3))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    a = np.clip(rr - np.hypot(xx - cx, yy - cy) + 0.5, 0, 1)[..., None] * alpha
    region = px[y0:y1, x0:x1]
    px[y0:y1, x0:x1] = region + (np.asarray(colour, np.float32) - region) * a


def glow_disc(px: Pixels, kit: Kit, x: float, y: float, r: float, colour: Sequence[float], strength: float) -> None:
    """A soft additive halo around (x, y): a moving part's glow, which can't wait for a blur."""
    s = kit.s
    cx, cy, rr = x * s, y * s, r * s
    x0, x1 = max(0, int(cx - 3 * rr)), min(kit.size, int(cx + 3 * rr))
    y0, y1 = max(0, int(cy - 3 * rr)), min(kit.size, int(cy + 3 * rr))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    a = np.exp(-((np.hypot(xx - cx, yy - cy) / rr) ** 2))[..., None] * strength
    add(px, np.s_[y0:y1, x0:x1], np.asarray(colour, np.float32) * a)


class Frame:
    """The still part of a frame being drawn. Each coloured shape also lights a layer that, blurred, becomes the glow
    around it; the shapes go over the glow (on top it would wash their colour out to white), the text over both."""

    def __init__(self, kit: Kit, theme: Theme, tint: Sequence[float] | None = None, strength: float = 0.0) -> None:
        self.kit, self.theme = kit, theme
        self.px = kit.background(theme).copy()
        if tint is not None:
            self.px += kit.ambient * np.array(tint, np.float32) * strength
        self.light = np.zeros_like(self.px)
        self.shapes: list[Callable[[F32], None]] = []
        self.text: dict[tuple[int, int, int], Image.Image] = {}  # colour -> its mask

    def paint(self, ring: Ring, alpha: F32, colour: Sequence[float] | F32, glow: float = 1.0) -> None:
        if glow:
            on = alpha > 0
            lit = colour[on] if np.ndim(colour) == 2 else np.asarray(colour, np.float32)  # type: ignore[call-overload]
            self.light.reshape(-1, 3)[ring.idx[on]] += lit * alpha[on, None] * glow
        self.shapes.append(lambda px: paint(px, ring, alpha, colour))

    def rect(self, x: float, y: float, w: float, h: float, colour: Sequence[float], glow: float = 1.0) -> None:
        s = self.kit.s
        sl = np.s_[round(y * s) : round((y + h) * s), round(x * s) : round((x + w) * s)]
        if glow:
            self.light[sl] += np.array(colour, np.float32) * glow

        def shape(px: F32) -> None:
            px[sl] = colour

        self.shapes.append(shape)

    def disc(self, x: float, y: float, r: float, colour: Sequence[float], glow: float = 1.0) -> None:
        if glow:
            disc(self.light, self.kit, x, y, r, np.array(colour, np.float32) * glow)  # type: ignore[arg-type]
        self.shapes.append(lambda px: disc(px, self.kit, x, y, r, colour))

    def draw(self, rgb: Sequence[float]) -> ImageDraw.ImageDraw:
        r, g, b = (int(c) for c in rgb)
        if (r, g, b) not in self.text:
            self.text[r, g, b] = Image.new("L", (self.kit.size, self.kit.size))
        return ImageDraw.Draw(self.text[r, g, b])

    def write(
        self,
        xy: tuple[float, float],
        s: str,
        weight: str,
        size: float,
        rgb: Sequence[float],
        anchor: str = "mm",
        spacing: float = 0,
        fit: float | None = None,
    ) -> None:
        """Text at xy. spacing: extra px between letters, for small capitals (centred on xy); fit: a radius the text
        must stay inside, which shrinks it (to 60 % at most) rather than let the panel's edge or a ring cut it."""
        if fit:
            size = fitted(self.kit, xy, s, weight, size, anchor, spacing, fit)
        k = self.kit
        font, draw = k.font(weight, size), self.draw(rgb)
        x, y = xy[0] * k.s, xy[1] * k.s
        if not spacing:
            draw.text((x, y), s, font=font, fill=255, anchor=anchor, features=["tnum"])
            return
        gap = spacing * k.s
        x -= (sum(k.advance(weight, size, c) for c in s) + gap * (len(s) - 1)) / 2
        for c in s:
            draw.text((x, y), c, font=font, fill=255, anchor="lm")
            x += k.advance(weight, size, c) + gap

    def number(
        self,
        y: float,
        value: float | None,
        unit: str,
        size: float = 132,
        rgb: Sequence[float] | None = None,
        glow: Sequence[float] | None = None,
        fit: float = 150,
    ) -> None:
        """A big number with its unit set small at its cap height, baseline at y: the digits' ink centred on the
        panel and the unit hanging to its right (centring the pair would push the heavy digits left of centre),
        shrunk to stay inside the circle of radius fit. A missing value is a calm dash, without its unit."""
        k, colour = self.kit, rgb or self.theme.text
        if value is None:
            self.write((MID, y - size * 0.36), DASH, "Bold", size * 0.55, self.theme.dim)
            return
        s = f"{value:.0f}"
        while True:
            big, small = k.font("Black", size), k.font("Bold", size / 3)
            ink0, _, ink1, _ = (v / k.s for v in big.getbbox(s, anchor="ls", features=["tnum"]))
            x = MID - (ink0 + ink1) / 2  # where the digits start so that their ink is centred
            ux = x + ink1 + size * 0.045
            if size <= 60 or inside((x + ink0, y - size * 0.73, ux + small.getlength(unit) / k.s, y), fit):
                break
            size = round(size * 0.96)
        self.write((x, y), s, "Black", size, colour, anchor="ls")
        self.write((ux, y - size * 0.73), unit, "Bold", size / 3, colour, anchor="lt")
        if glow is not None:  # the number lights its own glow
            r, g, b = (int(c) for c in colour)
            box, a = coverage(self.text[r, g, b])
            self.light[box] += a * np.array(glow, np.float32) * 0.5

    def finish(self) -> Still:
        """(picture without text, text layers): the glow blurred at a quarter of the size, the shapes over it."""
        light = Image.fromarray(np.clip(self.light, 0, 255).astype(np.uint8)).reduce(4)
        size = self.kit.size
        glow = light.filter(ImageFilter.GaussianBlur(3.5 * self.kit.s)).resize((size, size), Image.Resampling.BILINEAR)
        px = self.px + np.asarray(glow, np.float32) * 0.9
        for shape in self.shapes:
            shape(px)
        return px, [(rgb, *coverage(m)) for rgb, m in self.text.items()]


def extent(
    kit: Kit, xy: tuple[float, float], s: str, weight: str, size: float, anchor: str, spacing: float
) -> tuple[float, float, float, float]:
    """The box text would cover, in 400 px."""
    font = kit.font(weight, size)
    if spacing:
        w = sum(kit.advance(weight, size, c) for c in s) / kit.s + spacing * (len(s) - 1)
        _, top, _, bottom = font.getbbox(s, anchor="mm")
        return xy[0] - w / 2, xy[1] + top / kit.s, xy[0] + w / 2, xy[1] + bottom / kit.s
    x0, y0, x1, y1 = font.getbbox(s, anchor=anchor, features=["tnum"])
    return xy[0] + x0 / kit.s, xy[1] + y0 / kit.s, xy[0] + x1 / kit.s, xy[1] + y1 / kit.s


@functools.lru_cache(maxsize=4096)  # a label or a reading that recurs is measured once
def fitted(
    kit: Kit, xy: tuple[float, float], s: str, weight: str, size: float, anchor: str, spacing: float, fit: float
) -> float:
    """The largest size, down to 60 % of size, at which the text stays inside the circle of radius fit."""
    floor = size * 0.6
    while size > floor and not inside(extent(kit, xy, s, weight, size, anchor, spacing), fit):
        size = max(floor, round(size * 0.95 * 2) / 2)
    return size


def coverage(mask: Image.Image) -> tuple[Region, NDArray[Any]]:
    """The box a text mask covers, and its coverage there (0-1)."""
    x0, y0, x1, y1 = mask.getbbox() or (0, 0, 0, 0)
    return np.s_[y0:y1, x0:x1], np.asarray(mask.crop((x0, y0, x1, y1)), np.float32)[..., None] / 255


def with_text(px: F32, layers: list[TextLayer]) -> Image.Image:
    """The finished picture: the text layers blended over px (in place), as 8-bit RGB."""
    for rgb, box, a in layers:
        px[box] += (np.array(rgb, np.float32) - px[box]) * a
    return Image.fromarray(np.clip(px, 0, 255).astype(np.uint8))
