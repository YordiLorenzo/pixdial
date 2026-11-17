"""Options for the opt-in hardware test (test_hardware.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixdial.sources import hwmon


@pytest.fixture(autouse=True)
def fake_default_hwmon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default sources must not discover the host's PSU or other sensors during tests."""
    monkeypatch.setattr(hwmon, "HWMON", tmp_path / "hwmon")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware-seconds",
        type=float,
        default=600.0,
        help="how long `-m hardware` sends frames to the panels before it resets them (default 600)",
    )
