"""Helpers the tests share."""

from __future__ import annotations

import logging


class Lines(logging.Handler):
    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def logged(lines: list[str]) -> logging.Logger:
    """A logger of its own that keeps each message in lines."""
    log = logging.Logger("test")
    log.addHandler(Lines(lines))
    return log
