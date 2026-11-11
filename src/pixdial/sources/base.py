"""The Source base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from ..readings import Reading


class Source(ABC):
    """read() returns the readings by key (see the README for the keys the built-in designs read). A reading it
    can't give now is left out; read() raises OSError or ValueError when the source can't be read at all, and is
    called again a period later. A reading that hasn't come for stale_after seconds counts as missing."""

    period = 1.0
    note: ClassVar[str] = ""  # what `list` prints beside its name, such as "experimental"

    @property
    def stale_after(self) -> float:
        return max(5.0, 3 * self.period)

    @abstractmethod
    def read(self) -> Mapping[str, Reading]: ...

    def gives(self) -> frozenset[str] | None:
        """The reading keys it can give on this machine, said without reading it (the default rotation leaves out
        the designs no source gives what they need); None when it can't say, which leaves every design in."""
        return None

    def reset(self) -> None:
        """After the machine resumed from sleep: drop handles that may not have survived it."""

    def close(self) -> None:
        """When the program stops."""
