"""Log lines for things that break, and once more when they work again."""

from __future__ import annotations

from collections.abc import Callable


class Report:
    """report(what, error): a line when something breaks or breaks differently, and one when it works again;
    report(what, **info): a line with news about it (a panel's firmware, the designs shown)."""

    def __init__(self, write: Callable[[str], None] = lambda line: print(line, flush=True)) -> None:
        self.write = write
        self.faults: dict[str, str] = {}

    def __call__(self, what: str, error: object = None, **info: object) -> None:
        if error is None:
            if self.faults.pop(what, None) or info:
                self.write(f"{what}: working" + "".join(f", {k} {v}" for k, v in info.items()))
        elif self.faults.get(what) != str(error):
            self.faults[what] = str(error)
            self.write(f"{what}: {error}")
