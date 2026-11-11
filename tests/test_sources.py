"""The built-in sources against fake /proc and /sys trees, and the sampler that runs them."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from pixdial.readings import Reading
from pixdial.runtime import Report, Sampler
from pixdial.sources import Command, Cpu, Hwmon, Rapl, Source
from tests import logged


def chip(root: Path, n: int, name: str, files: dict[str, str]) -> None:
    d = root / f"hwmon{n}"
    d.mkdir(parents=True)
    (d / "name").write_text(name + "\n")
    for file, text in files.items():
        (d / file).write_text(text + "\n")


@pytest.fixture
def hwmon(tmp_path: Path) -> Path:
    chip(tmp_path, 1, "k10temp", {"temp1_input": "61250", "temp1_label": "Tctl"})
    psu = {"power1_input": "312000000", "fan1_input": "0", "temp1_input": "41000", "temp1_crit": "70000"}
    chip(tmp_path, 4, "corsairpsu", {**psu, "temp2_input": "44500", "temp2_crit": "75000"})
    return tmp_path


def test_hwmon_by_label_and_by_file(hwmon: Path) -> None:
    source = Hwmon(
        {"cpu_c": "k10temp/Tctl", "psu_w": "corsairpsu/power1", "psu_fan": "corsairpsu/fan1"}, root=str(hwmon)
    )
    assert source.read() == {
        "cpu_c": Reading(61.25, "°C"),
        "psu_w": Reading(312.0, "W"),
        "psu_fan": Reading(0.0, "rpm"),
    }


def test_hwmon_list_takes_the_highest_and_the_lowest_limit(hwmon: Path) -> None:
    source = Hwmon({"psu_c": ["corsairpsu/temp1", "corsairpsu/temp2", "nct6798/temp1"]}, root=str(hwmon))
    assert source.read() == {"psu_c": Reading(44.5, "°C", max=70.0)}


def test_hwmon_looks_again_after_a_chip_moves(hwmon: Path) -> None:
    source = Hwmon({"psu_w": "corsairpsu/power1"}, root=str(hwmon))
    source.read()
    (hwmon / "hwmon4").rename(hwmon / "hwmon7")  # the PSU's cable replugged
    with pytest.raises(FileNotFoundError):
        source.read()
    assert source.read() == {"psu_w": Reading(312.0, "W")}


def test_hwmon_reads_every_chip_of_a_name(tmp_path: Path) -> None:
    chip(tmp_path, 2, "coretemp", {"temp1_input": "55000", "temp1_label": "Package id 0"})
    chip(tmp_path, 3, "coretemp", {"temp1_input": "71000", "temp1_label": "Package id 1"})
    source = Hwmon({"cpu_c": ["coretemp/Package id 0", "coretemp/Package id 1"]}, root=str(tmp_path))
    assert source.read() == {"cpu_c": Reading(71.0, "°C")}


def test_hwmon_names_what_it_did_not_find(hwmon: Path) -> None:
    with pytest.raises(FileNotFoundError, match="cpu_c: no hwmon sensor coretemp/Package id 0"):
        Hwmon({"cpu_c": "coretemp/Package id 0"}, root=str(hwmon)).read()


def test_cpu_load_from_two_samples(tmp_path: Path) -> None:
    stat = tmp_path / "stat"
    stat.write_text("cpu 100 0 100 800 0 0 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0\ncpu1 50 0 50 400 0 0 0 0\n")
    cpu = Cpu(str(stat))
    assert cpu.read() == {}
    stat.write_text("cpu 200 0 200 900 0 0 0 0 0 0\ncpu0 150 0 150 400 0 0 0 0\ncpu1 50 0 50 500 0 0 0 0\n")
    r = cpu.read()
    assert r["cpu_load"].value == pytest.approx(200 / 3)
    np.testing.assert_allclose(r["threads"].value, [100.0, 0.0])


def test_rapl_power_from_the_energy_counter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    counter = tmp_path / "energy_uj"
    counter.write_text("1000000")
    times = iter([10.0, 12.0, 13.0])
    monkeypatch.setattr("pixdial.sources.cpu.time.monotonic", lambda: next(times))
    rapl = Rapl(str(counter))
    assert rapl.read() == {}
    counter.write_text("201000000")
    assert rapl.read() == {"cpu_w": Reading(100.0, "W")}
    counter.write_text("5")  # wrapped
    assert rapl.read() == {}


def test_command_reads_json_or_one_number() -> None:
    script = 'import json; print(json.dumps({"fan": 900, "temps": [40, 50], "pump": {"value": 61, "unit": "°C"}}))'
    r = Command([sys.executable, "-c", script]).read()
    assert r["fan"] == Reading(900.0)
    np.testing.assert_array_equal(r["temps"].value, [40.0, 50.0])
    assert r["pump"] == Reading(61.0, "°C")
    limits = '{"x": {"value": 100, "max": "450"}}'
    assert Command([sys.executable, "-c", f"print({limits!r})"]).read() == {"x": Reading(100.0, max=450.0)}
    assert Command([sys.executable, "-c", "print(3.5)"], key="x").read() == {"x": Reading(3.5)}
    with pytest.raises(ValueError, match="not a number"):
        Command([sys.executable, "-c", "print('nan')"], key="x").read()
    for bad in ('{"x": []}', '{"x": [[1, 2]]}', '{"x": {"value": 1, "label": 5}}'):
        with pytest.raises(ValueError, match=r"not a number|must be text"):
            Command([sys.executable, "-c", f"print({bad!r})"]).read()
    with pytest.raises(OSError):
        Command([sys.executable, "-c", "raise SystemExit(1)"]).read()


class Flaky(Source):
    period = 0.5

    def __init__(self) -> None:
        self.calls = 0

    def read(self) -> dict[str, Reading]:
        self.calls += 1
        if self.calls == 2:
            raise OSError("sensor gone")
        return {"x": Reading(float(self.calls))}


def test_the_sampler_reports_a_failure_once_and_its_recovery() -> None:
    lines: list[str] = []
    flaky = Flaky()
    sampler = Sampler([("flaky", flaky)], Report(logged(lines)), clock=lambda: 0.0)
    for _ in range(3):
        sampler.sample(0)
    assert lines == ["flaky: sensor gone", "flaky: working"]
    assert sampler.fresh(0.0) == {"x": Reading(3.0)}
    assert sampler.fresh(5.0) == {}  # stale after max(5 s, 3 periods)


def test_hwmon_keeps_the_readings_it_can_read(hwmon: Path) -> None:
    source = Hwmon({"cpu_c": "k10temp/Tctl", "psu_w": "corsairpsu/power1"}, root=str(hwmon))
    (hwmon / "hwmon4" / "power1_input").unlink()  # the PSU's cable out
    assert source.read() == {"cpu_c": Reading(61.25, "°C")}


class Constant(Source):
    def __init__(self, value: float, period: float) -> None:
        self.value, self.period = value, period

    def read(self) -> dict[str, Reading]:
        return {"x": Reading(self.value)}


def test_a_later_source_wins_a_key_two_report() -> None:
    sources: list[tuple[str, Source]] = [("first", Constant(1.0, 1.0)), ("second", Constant(2.0, 5.0))]
    sampler = Sampler(sources, Report(), clock=lambda: 0.0)
    sampler.sample(1)
    sampler.sample(0)  # the first source, read after the second
    assert sampler.fresh(0.0) == {"x": Reading(2.0)}
    assert sampler.fresh(6.0) == {"x": Reading(2.0)}
    assert sampler.fresh(15.0) == {}  # stale: 5 s for the first, 3 periods (15 s) for the second


class Slow(Source):
    def __init__(self, release: threading.Event) -> None:
        self.release = release

    def read(self) -> dict[str, Reading]:
        self.release.wait(5)
        return {}


def test_a_slow_source_holds_up_no_other() -> None:
    release = threading.Event()
    sources: list[tuple[str, Source]] = [("slow", Slow(release)), ("fast", Constant(1.0, 0.01))]
    sampler = Sampler(sources, Report())
    sampler.start()
    try:
        deadline = time.monotonic() + 2
        while not sampler.fresh(time.monotonic()) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert sampler.fresh(time.monotonic()) == {"x": Reading(1.0)}
    finally:
        sampler.stop()
        release.set()


def test_readings_from_before_a_sleep_are_dropped() -> None:
    sampler = Sampler([("first", Constant(1.0, 1.0))], Report(), clock=lambda: 0.0)
    sampler.sample(0)
    sampler.resumed()
    assert sampler.fresh(0.0) == {}


class Asleep(Source):
    """A source whose first read is under way as the machine sleeps; it hands back a reading from before."""

    period = 0.01

    def __init__(self) -> None:
        self.reading, self.woke, self.again, self.done = (threading.Event() for _ in range(4))
        self.resets = 0

    def read(self) -> dict[str, Reading]:
        if not self.reading.is_set():
            self.reading.set()
            self.woke.wait(5)
            return {"x": Reading(1.0)}
        self.again.set()
        self.done.wait(5)
        return {}

    def reset(self) -> None:
        self.resets += 1


def test_a_reading_begun_before_a_sleep_is_dropped_and_the_source_reset() -> None:
    source = Asleep()
    sampler = Sampler([("asleep", source)], Report())
    sampler.start()
    try:
        assert source.reading.wait(2)
        sampler.resumed()
        source.woke.set()
        assert source.again.wait(2)  # the first read is over
        assert sampler.fresh(time.monotonic()) == {}
        assert source.resets == 1
    finally:
        sampler.stop()
        source.done.set()
