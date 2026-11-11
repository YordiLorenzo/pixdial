"""Log lines for things that break, and once more when they work again; where `run` logs."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .. import NAME

LOG = logging.getLogger(NAME)


class Report:
    """report(what, error): a warning when something breaks or breaks differently, and a line when it works again;
    report(what, **info): a line with news about it (a panel's firmware, the designs shown). An error is text or an
    exception: an OSError or a ValueError (which says what it read) by its message, anything else with its type;
    with its traceback when debugging."""

    def __init__(self, log: logging.Logger = LOG) -> None:
        self.log = log
        self.faults: dict[str, str] = {}

    def __call__(self, what: str, error: BaseException | str | None = None, **info: object) -> None:
        if error is None:
            if self.faults.pop(what, None) or info:
                self.log.info(f"{what}: working" + "".join(f", {k} {v}" for k, v in info.items()))
            return
        text = (
            error if isinstance(error, str) else str(error) if isinstance(error, OSError | ValueError) else repr(error)
        )
        if self.faults.get(what) != text:
            self.faults[what] = text
            trace = error if isinstance(error, BaseException) and self.log.isEnabledFor(logging.DEBUG) else None
            self.log.warning(f"{what}: {text}", exc_info=trace)


def logs(debug: bool = False, file: Path | None = None) -> None:
    """`run`'s log: to stdout (the journal, under systemd) or a file, with the time in a file. When debugging: each
    USB command, the tracebacks, and each line's level and thread (a panel or a source)."""
    handler = logging.FileHandler(file) if file else logging.StreamHandler(sys.stdout)
    form = ("%(asctime)s " if file else "") + ("%(levelname)s [%(threadName)s] " if debug else "") + "%(message)s"
    handler.setFormatter(logging.Formatter(form))
    LOG.addHandler(handler)
    LOG.setLevel(logging.DEBUG if debug else logging.INFO)
