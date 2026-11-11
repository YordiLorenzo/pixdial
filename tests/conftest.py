"""Options for the opt-in hardware test (test_hardware.py)."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware-seconds",
        type=float,
        default=600.0,
        help="how long `-m hardware` sends frames to the panels before it resets them (default 600)",
    )
