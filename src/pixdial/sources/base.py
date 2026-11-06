"""The Source base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from ..readings import Reading


class Source(ABC):
    """read() returns the readings by key (see the README for the keys the built-in designs read). A reading it
    can't give now is left out; read() raises OSError or ValueError when the source can't be read at all, and is
    called again a period later. A reading that hasn't come for stale_after seconds counts as missing."""

    period = 1.0

    @property
    def stale_after(self) -> float:
        return max(5.0, 3 * self.period)

    @abstractmethod
    def read(self) -> Mapping[str, Reading]: ...

    def reset(self) -> None:
        """After the machine resumed from sleep: drop handles that may not have survived it."""

    def close(self) -> None:
        """When the program stops."""
