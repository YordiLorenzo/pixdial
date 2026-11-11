"""The Device base class, and what discovery finds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class Found:
    """A panel attached now: its id (what a config names it by), where it is, whether this user may open it, and
    what has it open now ("" while nothing has)."""

    id: str
    where: str
    access: bool
    held: str = ""


class Device(ABC):
    """One panel. open() may fail with OSError (unplugged, held by another program, no permission): the runtime
    tries again later. show() and off() may fail the same way once open, after which it closes and reopens it."""

    size = (400, 400)
    id = ""  # what discover() calls it (a serial)

    @classmethod
    def discover(cls) -> list[Found]:
        """The panels of this kind attached now."""
        return []

    def problem(self) -> str | None:
        """What would keep it from opening now (not attached, no permission), without opening it; None if nothing."""
        return None

    @abstractmethod
    def open(self) -> str:
        """Opens the panel; returns what to log about it (a firmware version)."""

    @abstractmethod
    def show(self, image: Image.Image) -> None:
        """Shows a picture of the panel's size, as it should look on the panel."""

    @abstractmethod
    def off(self) -> None:
        """Dark, for when the program stops, so no panel keeps showing old numbers."""

    @abstractmethod
    def close(self) -> None:
        """Lets go of the panel; it may be opened again."""
