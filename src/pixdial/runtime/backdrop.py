"""A panel's own picture under its design: a photo, or an animation (GIF, APNG, WebP), decoded once.

A backdrop file is untrusted input to Pillow: only these four formats open, the canvas and the frame count are read
from the header and checked before a pixel is decoded, and the decoded frames a panel keeps are capped.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import PIL
from numpy.typing import NDArray
from PIL import Image, ImageOps

FORMATS = ["PNG", "JPEG", "GIF", "WEBP"]  # an APNG opens as PNG
PILLOW = (13, 0, 0)  # the oldest Pillow that may decode one
MAX_PIXELS = 4096 * 4096  # a frame's canvas at most
MAX_FRAMES = 100_000  # frames in the file at most
MEMORY = 64_000_000  # bytes of decoded frames a backdrop keeps: 133 frames at 400 x 400
DECODE = 512_000_000  # canvas pixels decoded at most: about 3 s of decoding for a 2-megapixel GIF's 133 frames
SHORTEST = 0.02  # s: a frame shown for less (or for no time) is shown for DEFAULT, as browsers do
DEFAULT = 0.1  # s
# The picture's brightness: MIDDLE where the readings are, falling to EDGE at the panel's edge, where the gauges are,
# from EDGE_FROM of the way out; white text on a bright photo needs the middle dimmed too
MIDDLE, EDGE, EDGE_FROM = 0.65, 0.25, 0.5

Frame8 = NDArray[np.uint8]


class BackdropError(ValueError):
    pass


@dataclass(frozen=True)
class Pictures:
    """A backdrop's frames at one size, cover-fitted to the circle with a dark edge; ends: when each frame ends, in s
    from the start of the loop; total: the frames in the file (more than kept when the rest did not fit)."""

    frames: tuple[Frame8, ...]
    ends: NDArray[np.float64]
    total: int

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    @property
    def fps(self) -> float:
        """The rate of its shortest frame."""
        return float(1 / np.diff(self.ends, prepend=0.0).min())

    def index(self, now: float) -> int:
        """The frame to show at now."""
        return int(np.searchsorted(self.ends, now % self.ends[-1], side="right")) % len(self.frames)


class Backdrop:
    """A picture file, checked as it is made; at() decodes it once for each canvas size asked for."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sized: dict[int, Pictures] = {}
        if (version := tuple(int(p) for p in PIL.__version__.split(".")[:3])) < PILLOW:
            raise BackdropError(
                f"a backdrop needs Pillow {'.'.join(map(str, PILLOW))} or newer to decode it safely; this is "
                f"Pillow {'.'.join(map(str, version))}"
            )
        self.open().close()  # its checks

    def open(self) -> Image.Image:
        """The file opened, its header checked; nothing decoded yet."""
        try:
            image = Image.open(self.path, formats=FORMATS)
        except FileNotFoundError:
            raise BackdropError(f"no such file: {self.path}") from None
        except Image.DecompressionBombError:  # Pillow's own limit, far above ours
            raise BackdropError(f"{self.path}: a backdrop has at most {MAX_PIXELS:,} pixels") from None
        except OSError as error:  # Pillow's "cannot identify image file" for any other format
            raise BackdropError(f"{self.path}: not a PNG, JPEG, GIF or WebP picture ({error})") from None
        width, height = image.size
        frames = getattr(image, "n_frames", 1)  # a GIF's are counted without decoding them
        if width * height > MAX_PIXELS or frames > MAX_FRAMES:
            image.close()
            raise BackdropError(
                f"{self.path}: {width} x {height} with {frames} frames; a backdrop has at most {MAX_PIXELS:,} pixels "
                f"and {MAX_FRAMES:,} frames"
            )
        return image

    def at(self, size: int) -> Pictures:
        """Its frames at size x size (the runtime asks for one size only), decoded the first time."""
        if size not in self.sized:
            self.sized[size] = self.decode(size)
        return self.sized[size]

    def decode(self, size: int) -> Pictures:
        """Its frames from the first, as many as MEMORY and DECODE allow."""
        with self.open() as image:
            total = getattr(image, "n_frames", 1)
            keep = max(1, min(total, MEMORY // (size * size * 3), DECODE // (image.size[0] * image.size[1])))
            frames, ends, end = [], [], 0.0
            for i in range(keep):
                image.seek(i)
                frames.append(fit(image, size))
                duration = image.info.get("duration") or 0
                end += duration / 1000 if duration / 1000 >= SHORTEST else DEFAULT
                ends.append(end)
        return Pictures(tuple(frames), np.array(ends), total)


def fit(image: Image.Image, size: int) -> Frame8:
    """A frame cover-fitted to size x size (the circle's square) over black, darker towards the edge."""
    rgba = image.convert("RGBA")
    frame = Image.alpha_composite(Image.new("RGBA", rgba.size, (0, 0, 0, 255)), rgba).convert("RGB")
    fitted = np.asarray(ImageOps.fit(frame, (size, size), Image.Resampling.LANCZOS), np.float32)
    return (fitted * edge(size)).astype(np.uint8)


@functools.cache
def edge(size: int) -> NDArray[np.float32]:
    """MIDDLE in the middle, falling smoothly to EDGE at the panel's edge and past it."""
    mid = (size - 1) / 2
    y, x = np.mgrid[0:size, 0:size]
    t = np.clip((np.hypot(x - mid, y - mid) / (size / 2) - EDGE_FROM) / (1 - EDGE_FROM), 0, 1)
    darker: NDArray[np.float32] = (MIDDLE + (EDGE - MIDDLE) * t * t * (3 - 2 * t))[..., None].astype(np.float32)
    return darker
