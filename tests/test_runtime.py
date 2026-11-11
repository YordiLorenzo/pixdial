"""The runtime's timing, on a fake clock: when frames go out, how often the still part is drawn, rotation, fades,
retries, resume from sleep and layout changes. A few run the real loop and its threads on the real clock."""

from __future__ import annotations

import errno
import itertools
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixdial.designs import BUILTIN, THEMES, Design, Eased, Still, Theme
from pixdial.devices import Device
from pixdial.readings import Reading, Value
from pixdial.runtime import Catalog, Feed, Layout, Report, Runner, Sampler, Screen
from pixdial.runtime.runner import FAST, SLOW
from pixdial.sources import Source
from tests import logged


class Clock:
    def __init__(self) -> None:
        self.now, self.asleep, self.epoch = 1000.0, 0.0, 1_800_000_000.0

    def monotonic(self) -> float:
        return self.now

    def boottime(self) -> float:
        return self.now + self.asleep

    def wall(self) -> float:
        return self.epoch + self.now


class Live(Clock):
    """The real clocks."""

    def monotonic(self) -> float:
        return time.monotonic()

    def boottime(self) -> float:
        return time.monotonic() + self.asleep

    def wall(self) -> float:
        return time.time()


class Panel(Device):
    def __init__(self, fails: int = 0, error: Exception | None = None) -> None:
        self.fails, self.opens, self.closes = fails, 0, 0
        self.error = error  # what show() raises
        self.opened: list[float] = []  # when each open() came
        self.frames: list[tuple[float, Image.Image]] = []
        self.dark = False
        self.clock: Clock | None = None

    def open(self) -> str:
        assert self.clock is not None
        self.opens += 1
        self.opened.append(self.clock.monotonic())
        if self.fails:
            self.fails -= 1
            raise OSError("busy")
        return "fake"

    def show(self, image: Image.Image) -> None:
        assert self.clock is not None
        if self.error:
            raise self.error
        self.frames.append((self.clock.monotonic(), image))

    def off(self) -> None:
        self.dark = True

    def close(self) -> None:
        self.closes += 1


class Fixed(Source):
    """Stands for the sources; the rig sets what it read."""

    def read(self) -> dict[str, Reading]:
        return {}


class Rig:
    """A runner with fake panels on a fake clock; the readings are set by hand."""

    def __init__(
        self,
        tmp_path: Path,
        designs: tuple[str, ...],
        panels: list[Panel] | None = None,
        more: dict[str, type[Design]] | None = None,
        live: bool = False,
    ) -> None:
        self.clock = Live() if live else Clock()
        self.lines: list[str] = []
        self.readings: dict[str, Value] = {}
        report = Report(logged(self.lines))
        self.panels = panels or [Panel() for _ in designs]
        for panel in self.panels:
            panel.clock = self.clock
        catalog = Catalog({**BUILTIN, **(more or {})}, THEMES, "warm")
        self.layout = Layout(catalog, len(self.panels), tmp_path / "layout", designs, list(catalog.designs), 60)
        self.sampler = Sampler([("readings", Fixed())], report, self.clock.monotonic)
        screens = [Screen(str(i), p, report, self.clock.monotonic) for i, p in enumerate(self.panels)]
        feed = Feed({}, {spec for cls in BUILTIN.values() for spec in cls.trails})
        self.runner = Runner(screens, self.sampler, feed, catalog, self.layout, report, self.clock)  # type: ignore[arg-type]

    def set(self, **values: Value) -> None:
        """Readings the sources keep reporting."""
        self.readings = values
        self.sample()

    def sample(self) -> None:
        self.sampler.values = [{k: (Reading(v), self.clock.monotonic()) for k, v in self.readings.items()}]

    def tick(self) -> float:
        """One tick, with what each panel's thread would do before and after it."""
        self.pump()
        delay = self.runner.tick()
        self.pump()
        return delay

    def pump(self) -> None:
        for screen in self.runner.screens:
            screen.sender.step()

    def run_for(self, seconds: float) -> list[float]:
        """Ticks for that long, as the loop would; returns the delays."""
        delays, end = [], self.clock.now + seconds
        while self.clock.now < end - 1e-9:
            self.sample()
            delay = self.tick()
            delays.append(delay)
            self.clock.now += delay
        return delays

    def run_live(self, seconds: float) -> None:
        """The runner's own loop and threads on the real clock, for that long."""
        stop = threading.Event()
        loop = threading.Thread(target=self.runner.run, args=(stop,))
        loop.start()
        time.sleep(seconds)
        stop.set()
        loop.join(10)


def test_a_still_screen_sends_once_then_every_30_s(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.set(cpu_c=40)
    delays = rig.run_for(65)
    sent = [t - 1000 for t, _ in rig.panels[0].frames]
    assert sent == pytest.approx([0, 30, 60], abs=0.11)
    assert delays == pytest.approx([SLOW] * len(delays))


def test_an_animation_runs_at_30_frames_a_second(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("psu",))
    rig.set(psu_w=300, working=2)
    delays = rig.run_for(2)
    assert delays == pytest.approx([FAST] * len(delays))
    assert len(rig.panels[0].frames) == pytest.approx(60, abs=1)


def test_the_still_part_is_drawn_at_most_10_times_a_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, ("psu",))
    rig.set(psu_w=100, working=1)
    rig.tick()
    design = rig.runner.screens[0].design
    assert design is not None
    draws: list[float] = []
    still = design.still

    def counted() -> Still:
        draws.append(rig.clock.now)
        return still()

    monkeypatch.setattr(design, "still", counted)
    for i in range(60):  # 2 s at 30 frames a second, the watts changing every frame
        rig.clock.now += FAST
        rig.set(psu_w=100 + 20 * i, working=1)
        rig.tick()
    gaps = [b - a for a, b in itertools.pairwise(draws)]
    assert len(draws) >= 10 and min(gaps) >= 0.1 - 1e-9


def test_rotation_steps_every_panel_each_minute_without_repeats(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("crown", "gpu", "psu"))
    rig.layout.save(["rotate"])
    rig.clock.epoch -= rig.clock.wall() % 60 - 1  # a second past the minute
    rig.tick()
    first = [s.spec for s in rig.runner.screens]
    assert len(set(first)) == 3
    rig.run_for(58.5)
    assert [s.spec for s in rig.runner.screens] == first
    delays = rig.run_for(1.0)
    second = [s.spec for s in rig.runner.screens]
    assert all(a != b for a, b in zip(first, second, strict=True)) and len(set(second)) == 3
    assert min(delays) == pytest.approx(FAST)  # fading in


def test_a_new_design_fades_in_over_the_last_frame(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.set(cpu_c=40)
    rig.run_for(1)
    rig.layout.save(["crown:ice"])
    rig.clock.now += 0.01
    frames = len(rig.panels[0].frames)
    delays = rig.run_for(0.6)
    faded = rig.panels[0].frames[frames:]
    assert 11 <= len(faded) <= 14  # 0.4 s at 30 frames a second, then none: crown is still
    assert delays[0] == pytest.approx(FAST) and delays[-1] == pytest.approx(SLOW)


def test_a_panel_that_will_not_open_is_tried_after_a_wait_that_doubles(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",), [Panel(fails=7)])
    rig.set(cpu_c=40)
    rig.run_for(40)
    waits = [b - a for a, b in itertools.pairwise(rig.panels[0].opened)]
    assert waits == pytest.approx([0.25, 0.5, 1, 2, 4, 8, 10], abs=0.11)  # a tick's lag at most
    assert rig.panels[0].frames[0][0] == pytest.approx(1025.75, abs=0.11)
    assert [line for line in rig.lines if "panel" in line] == ["0 panel: busy", "0 panel: working, info fake"]


class Unplugged(Panel):
    """A panel pulled out at `out` and plugged in again at `back`, on the rig's clock."""

    def __init__(self, out: float, back: float) -> None:
        super().__init__()
        self.out, self.back = out, back

    def gone(self) -> bool:
        assert self.clock is not None
        return self.out <= self.clock.monotonic() < self.back

    def open(self) -> str:
        info = super().open()
        if self.gone():
            raise FileNotFoundError("no SL V3 LCD with serial 1")
        return info

    def show(self, image: Image.Image) -> None:
        if self.gone():
            raise OSError(errno.ENODEV, "No such device")
        super().show(image)


def test_a_resume_reopens_the_panels_at_once_and_resets_the_sources(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.set(cpu_c=40)
    rig.run_for(1)
    rig.clock.asleep += 3600
    rig.tick()
    assert rig.panels[0].closes == 1 and rig.panels[0].opens == 2
    assert rig.sampler.epoch == 1


def test_a_panel_slow_to_come_back_after_a_resume_is_back_soon_after_it_shows_up(tmp_path: Path) -> None:
    panel = Unplugged(1001, 1002.27)  # it takes 1.27 s to take a frame again, as two panels did on the rig
    rig = Rig(tmp_path, ("minimal",), [panel])
    rig.set(cpu_c=40)
    rig.run_for(1)
    rig.clock.asleep += 3600
    sent = len(panel.frames)
    rig.run_for(2)
    assert panel.opened[1:] == pytest.approx([1001, 1001.25, 1001.75, 1002.75], abs=0.11)
    assert panel.frames[sent][0] == pytest.approx(1002.75, abs=0.11)


def test_a_panel_unplugged_mid_run_is_back_soon_after_it_is_plugged_in(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("psu", "crown"), [Unplugged(1010, 1011), Panel()])
    rig.set(cpu_c=40, psu_w=300, working=2)  # psu animates: a frame every tick
    rig.run_for(15)
    back = [t for t, _ in rig.panels[0].frames if t >= 1010]
    # Tries at 10.25 and 10.75 s still find it gone; each of the 3 tries can lag a tick (1/30 s) on the rig's clock
    assert back and back[0] == pytest.approx(1011.75, abs=0.15)
    assert [line for line in rig.lines if line.startswith("0 panel")] == [
        "0 panel: working, info fake",
        f"0 panel: [Errno {errno.ENODEV}] No such device",
        "0 panel: no SL V3 LCD with serial 1",
        "0 panel: working, info fake",
    ]
    assert [t for t, _ in rig.panels[1].frames] == pytest.approx([1000], abs=0.11)  # still: nothing to send again


def test_a_bad_layout_file_keeps_the_designs(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.run_for(1)
    (tmp_path / "layout").write_text("crown nope\n")
    rig.run_for(1)
    assert rig.runner.screens[0].spec == "minimal"
    assert sum("layout:" in line and "nope" in line for line in rig.lines) == 1


def test_stale_readings_go_missing(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.set(cpu_c=40)
    assert rig.sampler.fresh(rig.clock.now + 4.9)
    assert not rig.sampler.fresh(rig.clock.now + 5.0)


def test_the_panels_go_dark_when_it_stops(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    stop = threading.Event()
    rig.tick()
    stop.set()
    rig.runner.run(stop)
    assert rig.panels[0].dark


def test_a_series_that_changes_length_starts_over() -> None:
    eased = Eased(1)
    eased.step(np.zeros(48), 0.1)
    assert eased.step(np.ones(47), 0.1) is not None and eased.value.shape == (47,)  # type: ignore[union-attr]


def test_a_failing_design_stops_only_its_own_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, ("minimal", "crown"))
    rig.set(cpu_c=40)
    rig.tick()
    broken = rig.runner.screens[0].design

    def update(r: object, now: float, dt: float) -> tuple[object, object]:
        raise ValueError("a reading it can't draw")

    monkeypatch.setattr(broken, "update", update)
    sent = len(rig.panels[1].frames)
    rig.run_for(31)  # past a resend
    assert len(rig.panels[1].frames) > sent
    assert sum("0 design minimal" in line for line in rig.lines) == 1


def test_a_design_that_fails_halfway_is_drawn_afresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.set(cpu_c=40)
    rig.runner.screens[0].use("minimal", rig.runner.catalog.make)
    design = rig.runner.screens[0].design
    assert design is not None
    fails = [1]
    moving = design.moving

    def flaky(px: object, now: float) -> None:
        if fails[0]:
            fails[0] -= 1
            raise ValueError("halfway")
        moving(px, now)  # type: ignore[arg-type]

    monkeypatch.setattr(design, "moving", flaky)
    rig.run_for(0.3)
    assert len(rig.panels[0].frames) == 1  # the second tick drew it whole and sent it


class Broken(Design):
    """A plugin design with a bug in its __init__."""

    name, shows = "broken", "nothing"

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        raise RuntimeError("a bug in a plugin")


def test_a_design_that_fails_as_it_starts_stops_only_its_own_panel(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("broken", "minimal"), more={"broken": Broken})
    rig.set(cpu_c=40)
    rig.run_for(1)
    assert rig.panels[1].frames and not rig.panels[0].frames
    assert [line for line in rig.lines if "0 design" in line] == ["0 design broken: RuntimeError('a bug in a plugin')"]


def test_rotation_passes_a_design_that_fails_as_it_starts(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("rotate",), [Panel()], more={"broken": Broken})
    rig.layout.rotation = ["minimal", "broken", "crown"]
    rig.clock.epoch -= rig.clock.wall() % 180 - 1  # a second past a minute that starts the rotation
    rig.set(cpu_c=40)
    rig.run_for(90)
    assert rig.runner.screens[0].spec == "minimal"  # kept while the rotation is on the broken design
    sent = len(rig.panels[0].frames)
    rig.run_for(60)
    assert rig.runner.screens[0].spec == "crown" and len(rig.panels[0].frames) > sent
    assert sum("broken" in line for line in rig.lines) == 1


def test_a_device_error_other_than_oserror_stops_only_its_own_panel(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal", "crown"), [Panel(error=ValueError("frame too big")), Panel()])
    rig.set(cpu_c=40)
    rig.run_for(31)  # past a resend
    assert len(rig.panels[1].frames) == 2
    assert "0 panel: frame too big" in rig.lines


def test_a_series_on_a_trail_key_leaves_a_gap(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal", "crown"))
    rig.set(cpu_c=40, cpu_load=np.array([10.0, 20.0]), psu_w=np.array([100.0, 200.0]))  # a command source's lists
    rig.run_for(1)
    assert rig.panels[0].frames  # crown can't draw a list as its load: it reports that for its own panel
    assert all(np.isnan(trail.v).all() for trail in rig.runner.feed.trails.values())
    assert any(line.startswith("1 design crown: ") for line in rig.lines)


class Cheap(Design):
    """A new frame every tick that costs next to nothing to draw, so a test measures the runtime, not the drawing."""

    name, shows = "cheap", "a counter"

    def __init__(self, theme: Theme, scale: int = 1) -> None:
        super().__init__(theme, scale)
        self.count = 0

    def update(self, r: object, now: float, dt: float) -> tuple[int, int]:
        self.count += 1
        return 0, self.count

    def still(self) -> Still:
        return np.zeros((400, 400, 3), np.float32), []


class Hung(Panel):
    """A panel that stopped answering: every frame's write times out after usbfs's 1 s."""

    def show(self, image: Image.Image) -> None:
        time.sleep(1)
        raise TimeoutError(errno.ETIMEDOUT, "Connection timed out")


def test_a_hung_panel_holds_up_no_other(tmp_path: Path) -> None:
    hung = Hung()
    rig = Rig(tmp_path, ("cheap", "cheap"), [hung, Panel()], more={"cheap": Cheap}, live=True)
    rig.run_live(3)
    healthy = [t for t, _ in rig.panels[1].frames]
    assert len(healthy) / (healthy[-1] - healthy[0]) >= 25  # frames a second; 1 when the hung panel held it up
    lines = [line for line in rig.lines if line.startswith("0 panel")]
    assert len(lines) <= hung.opens  # the break, then one line per try at most (opens: the first, then the tries)


def test_a_panel_that_fails_every_frame_waits_longer_each_time_and_says_so_once(tmp_path: Path) -> None:
    panel = Panel(error=OSError(errno.EIO, "Input/output error"))
    rig = Rig(tmp_path, ("psu",), [panel])
    rig.set(psu_w=300, working=2)
    rig.run_for(60)
    waits = [b - a for a, b in itertools.pairwise(panel.opened)]
    assert waits == pytest.approx([0.25, 0.5, 1, 2, 4, 8, 10, 10, 10, 10], abs=0.04)  # a tick's lag at most
    assert [line for line in rig.lines if "panel" in line] == ["0 panel: [Errno 5] Input/output error"]


def test_a_panel_gets_the_newest_frame_and_no_older_one(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ("minimal",))
    rig.run_for(0.1)
    sent, frames = len(rig.panels[0].frames), [Image.new("RGB", (400, 400), (i, 0, 0)) for i in range(3)]
    for frame in frames:  # while the panel is busy with a frame before them
        rig.runner.screens[0].sender.post(frame)
    rig.pump()
    rig.pump()
    assert [image for _, image in rig.panels[0].frames[sent:]] == [frames[2]]


def test_a_panel_unplugged_mid_run_comes_back_on_the_real_clock(tmp_path: Path) -> None:
    start = time.monotonic()
    unplugged = Unplugged(start + 0.5, start + 1.0)
    rig = Rig(tmp_path, ("cheap", "cheap"), [unplugged, Panel()], more={"cheap": Cheap}, live=True)
    rig.run_live(2.5)
    back = [t for t, _ in unplugged.frames if t >= unplugged.back]
    assert back and back[0] - unplugged.back < 0.5  # tried 0.25 and 0.75 s after it went; 10 s later in 0.1.0
    lines = [line for line in rig.lines if line.startswith("0 panel")][1:]  # after it first worked
    assert len(lines) <= unplugged.opens  # the break, then one line per try at most (opens: the first, then the tries)
    healthy = [t for t, _ in rig.panels[1].frames]
    assert len(healthy) / (healthy[-1] - healthy[0]) >= 25


class ShutDown(Panel):
    """A panel whose transport shut down once, as one did on the rig right after a USB reset."""

    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def show(self, image: Image.Image) -> None:
        if not self.failed:
            self.failed = True
            raise OSError(errno.ESHUTDOWN, "Cannot send after transport endpoint shutdown")
        super().show(image)


def test_a_transport_shut_down_on_a_send_is_opened_again_after_the_first_wait(tmp_path: Path) -> None:
    panel = ShutDown()
    rig = Rig(tmp_path, ("psu",), [panel])
    rig.set(psu_w=300, working=2)
    rig.run_for(1)
    assert panel.closes == 1 and panel.opened == pytest.approx([1000, 1000.25], abs=0.04)
    assert panel.frames[0][0] == pytest.approx(1000.25, abs=0.04) and len(panel.frames) > 20
    assert [line for line in rig.lines if "panel" in line] == [
        f"0 panel: [Errno {errno.ESHUTDOWN}] Cannot send after transport endpoint shutdown",
        "0 panel: working, info fake",
    ]
