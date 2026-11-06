"""A panel that isn't there: each frame goes to a PNG file, for trying designs and the runtime without hardware."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from .base import Device


class Png(Device):
    """Writes every frame to path (whole, so a viewer never reads half a picture); off() writes a black one."""

    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser()
        self.id = str(self.path)

    def problem(self) -> str | None:
        folder = self.path.parent
        while not folder.exists():
            folder = folder.parent
        return None if os.access(folder, os.W_OK) else f"can't write in {folder}"

    def open(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return f"writing {self.path}"

    def show(self, image: Image.Image) -> None:
        part = self.path.with_name(self.path.name + ".part")
        image.save(part, "PNG")
        part.replace(self.path)

    def off(self) -> None:
        self.show(Image.new("RGB", self.size))

    def close(self) -> None:
        pass
