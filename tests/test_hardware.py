"""The opt-in test on real panels: `uv run pytest -m hardware`, which the normal run leaves out.

It sends frames to every SL V3 or TL panel attached, all at once at 30 frames a second, through pixdial's driver. It
checks that the panels acknowledge every frame and that resident memory stays flat. Then it resets each panel with
the USBDEVFS_RESET ioctl on its usbfs node (it needs only the access pixdial has) and times how long the panel takes
to acknowledge a frame again. It prints a short report. `--hardware-seconds` sets how long the frames run before
the resets (default 600). It refuses to start while another program has a panel open: stop pixdial.service first.
The tests after it check its logic in the normal run, against the fake panel of test_slv3.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import math
import os
import threading
import time
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image

from pixdial.designs import BUILTIN, THEMES
from pixdial.devices import slv3
from pixdial.gallery import Demo
from pixdial.runtime import Catalog

from .test_slv3 import Usb

FPS = 30
USBDEVFS_RESET = 0x5514  # _IO('U', 20)
RECOVERY = 30.0  # s a panel may take after its reset to acknowledge a frame again
SETTLE = 10.0  # s before the first memory sample, while Pillow and the allocator settle
FLAT = 5 * 2**20  # bytes resident memory may grow after that: a leak of one frame a second would be 6 MB a minute
STOP_PIXDIAL = "systemctl --user stop pixdial"


@dataclass
class Tally:
    """One panel's frames in one part of the test."""

    sent: int = 0
    acked: int = 0
    errors: Counter[str] = field(default_factory=Counter)
    written: float = -math.inf  # when its last write went out
    acked_for: float = -math.inf  # when the frame it acknowledged last was written
    acked_at: float = -math.inf  # when that acknowledgement came
    cpu: float = 0.0  # s its sender thread ran


class Counted:
    """A panel's transport that counts the frames acknowledged: replies that start with the frame command (the
    panel's replies start with the command they answer). A read answers the last write before it."""

    def __init__(self, usb: slv3.Transport, tally: Tally) -> None:
        self.usb, self.tally = usb, tally

    def write(self, data: bytearray, timeout_ms: int = 1000) -> None:
        self.usb.write(data, timeout_ms)
        self.tally.written = time.monotonic()

    def read(self, timeout_ms: int = 1000) -> bytes:
        answers = self.tally.written
        reply = self.usb.read(timeout_ms)
        if reply[:1] == bytes([slv3.FRAME]):
            self.tally.acked += 1
            self.tally.acked_for, self.tally.acked_at = answers, time.monotonic()
        return reply

    def close(self) -> None:
        self.usb.close()


@dataclass
class Result:
    seconds: float
    steady: dict[str, Tally]
    memory: list[int]  # resident bytes, once a second from SETTLE on, and at the end
    cpu: float  # s the process ran while the frames went out
    recovery: dict[str, float | None]  # s from each panel's reset to its next acknowledged frame
    after: dict[str, Tally]  # the frames around the resets


def send(panel: slv3.Slv3, tally: Tally, frames: Sequence[Image.Image], stop: threading.Event) -> None:
    """Frames to one panel at FPS until stop is set, opening it again after an error; then dark and closed. A late
    frame goes out at once and the next ones follow it, so a stall doesn't end in a burst."""
    opened, n, due = False, 0, time.monotonic()
    while not stop.is_set():
        try:
            if not opened:
                panel.open()
                opened = True
            panel.show(frames[n % len(frames)])
            tally.sent += 1
        except OSError as error:  # the panel reset or re-enumerating
            tally.errors[str(error)] += 1
            if opened:
                panel.close()
            opened = False
        n += 1
        due = max(due + 1 / FPS, time.monotonic())
        stop.wait(due - time.monotonic())
    if opened:
        with contextlib.suppress(OSError):
            panel.off()  # also reads the last frame's acknowledgement
        panel.close()
    tally.cpu = time.thread_time()


@contextlib.contextmanager
def sending(panels: Sequence[slv3.Slv3], tallies: Mapping[str, Tally], frames: Sequence[Image.Image]) -> Iterator[None]:
    stop = threading.Event()
    threads = [threading.Thread(target=send, args=(p, tallies[p.serial], frames, stop)) for p in panels]
    for t in threads:
        t.start()
    try:
        yield
    finally:
        stop.set()
        for t in threads:
            t.join()


def soak(
    panels: Sequence[slv3.Slv3],
    frames: Sequence[Image.Image],
    seconds: float,
    reset: Callable[[str], None],
    memory: Callable[[], int],
    limit: float = RECOVERY,
) -> Result:
    """Frames to every panel at once for seconds, then each panel reset in turn while all of them keep going."""
    tallies: dict[str, Tally] = {}  # the part under way's: each open counts into it
    connect = slv3.connect
    slv3.connect = lambda serial: Counted(connect(serial), tallies[serial])  # type: ignore[assignment,return-value]
    try:
        steady = tallies = {p.serial: Tally() for p in panels}
        samples: list[int] = []
        cpu, start = time.process_time(), time.monotonic()
        with sending(panels, steady, frames):
            while (now := time.monotonic()) < start + seconds:
                if now >= start + min(SETTLE, seconds / 2):
                    samples.append(memory())
                time.sleep(min(1.0, seconds / 10, start + seconds - now))
            samples.append(memory())
        cpu = time.process_time() - cpu
        after = tallies = {p.serial: Tally() for p in panels}
        with sending(panels, after, frames):
            recovery = {p.serial: recovered(p.serial, after[p.serial], reset, limit) for p in panels}
    finally:
        slv3.connect = connect
    return Result(seconds, steady, samples, cpu, recovery, after)


def recovered(serial: str, tally: Tally, reset: Callable[[str], None], limit: float) -> float | None:
    """Seconds from the panel's reset to the first acknowledgement of a frame written after it; None after limit."""
    working = time.monotonic() + limit
    while tally.acked == 0 and time.monotonic() < working:
        time.sleep(0.01)
    start = time.monotonic()
    reset(serial)
    done = time.monotonic()
    while time.monotonic() < start + limit:
        if tally.acked_for >= done:
            return tally.acked_at - start
        time.sleep(0.01)
    return None


def problems(r: Result) -> list[str]:
    out = []
    for serial, t in r.steady.items():
        if t.errors or t.acked != t.sent:
            out.append(f"{serial}: {t.acked} of {t.sent} frames acknowledged, errors {dict(t.errors)}")
        if t.sent / r.seconds < FPS - 1:
            out.append(f"{serial}: {t.sent / r.seconds:.1f} frames/s, not {FPS}")
    if max(r.memory) - r.memory[0] > FLAT:
        out.append(f"resident memory grew from {mib(r.memory[0])} to {mib(max(r.memory))}")
    out += [f"{serial}: no frame acknowledged after its reset" for serial, s in r.recovery.items() if s is None]
    return out


def report(r: Result, models: Mapping[str, str]) -> str:
    lines = [f"pixdial hardware test: {len(r.steady)} panels, {r.seconds:.0f} s at {FPS} frames/s"]
    for serial, t in r.steady.items():
        errors = f", errors {dict(t.errors)}" if t.errors else ""
        lines.append(
            f"  {serial} ({models[serial]}): {t.sent} frames sent, {t.acked} acknowledged, "
            f"{t.sent / r.seconds:.1f} frames/s, CPU {100 * t.cpu / r.seconds:.1f}% of one core{errors}"
        )
    lines.append(
        f"  all panels: CPU {100 * r.cpu / r.seconds:.1f}% of one core; resident memory {mib(r.memory[0])} at the "
        f"start, {mib(r.memory[-1])} at the end, {mib(max(r.memory))} at most"
    )
    for serial, s in r.recovery.items():
        took = "no acknowledged frame" if s is None else f"{s:.2f} s to the first acknowledged frame"
        errors = f", errors {dict(r.after[serial].errors)}" if r.after[serial].errors else ""
        lines.append(f"  {serial} after its USB reset: {took}{errors}")
    return "\n".join(lines)


def mib(n: int) -> str:
    return f"{n / 2**20:.1f} MiB"


def resident() -> int:
    """This process's resident memory in bytes (Linux)."""
    return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def reset(serial: str) -> None:
    """A USB reset of the panel through its usbfs node: the port is reset and the panel set up again."""
    node = next(d.node for d, _ in slv3.panels() if d.serial == serial)
    fd = os.open(node, os.O_RDWR)
    try:
        fcntl.ioctl(fd, USBDEVFS_RESET, 0)
    finally:
        os.close(fd)


def holders(nodes: Collection[str], proc: Path = Path("/proc")) -> list[str]:
    """The other processes this user can see that have one of these device nodes open, as "pid (name) node"."""
    found = []
    for fd in proc.glob("[0-9]*/fd/*"):
        with contextlib.suppress(OSError):  # the process ended, or isn't this user's
            if (node := str(fd.readlink())) in nodes and int(fd.parent.parent.name) != os.getpid():
                found.append(f"{fd.parent.parent.name} ({(fd.parent.parent / 'comm').read_text().strip()}) {node}")
    return found


def demo_frames() -> list[Image.Image]:
    """The psu design's animation, 30 frames a second from its busy demo readings: real pictures to encode."""
    return Demo(Catalog(BUILTIN, THEMES, "warm").make("psu"), "busy", {}).frames()


@pytest.mark.hardware
def test_real_panels(request: pytest.FixtureRequest, capsys: pytest.CaptureFixture[str]) -> None:
    found = slv3.Slv3.discover()
    if not found:
        pytest.fail("no SL V3 or TL panel attached")
    if denied := [f.where for f in found if not f.access]:
        pytest.fail(f"no read and write access to {', '.join(denied)} : `pixdial setup` gives it")
    if held := holders({d.node for d, _ in slv3.panels()}):
        pytest.fail(f"another program has a panel open: {'; '.join(held)}. Stop it first ({STOP_PIXDIAL})")
    panels = [slv3.Slv3(f.id) for f in found]
    for panel in panels:
        try:
            panel.open()
        except OSError as error:  # EBUSY: a program this user can't see (another user's, or root's) has claimed it
            pytest.fail(f"panel {panel.serial}: {error}. If another program has it, stop that first ({STOP_PIXDIAL})")
        panel.close()
    result = soak(panels, demo_frames(), request.config.getoption("--hardware-seconds"), reset, resident)
    with capsys.disabled():
        print("\n" + report(result, {f.id: f.note or "SL V3" for f in found}))
    assert not problems(result)


# ---------------------------------------------------------------- its logic, against fake panels


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Usb]]:
    """Each serial's fake panels, the newest last: every open connects to a new one."""
    connected: dict[str, list[Usb]] = {"A": [], "B": []}

    def connect(serial: str) -> Usb:
        connected[serial].append(Usb())
        return connected[serial][-1]

    monkeypatch.setattr(slv3, "connect", connect)
    return connected


FRAMES = [Image.new("RGB", (400, 400), (i * 60, 0, 0)) for i in range(4)]


def test_every_frame_is_counted_and_a_reset_panel_is_timed(fakes: dict[str, list[Usb]]) -> None:
    resets: list[str] = []
    r = soak([slv3.Slv3("A"), slv3.Slv3("B")], FRAMES, 0.4, resets.append, lambda: 50 * 2**20)
    assert resets == ["A", "B"]
    for serial in "AB":
        assert r.steady[serial].sent >= 6 and r.steady[serial].acked == r.steady[serial].sent
        assert r.steady[serial].cpu > 0
        frames = sum(c == slv3.FRAME for usb in fakes[serial] for c in usb.commands())
        assert frames == r.steady[serial].sent + r.after[serial].sent  # what the panels got, nothing more
    assert all(s is not None and s < 0.5 for s in r.recovery.values())
    assert [p for p in problems(r) if "frames/s" not in p] == []  # a busy CI runner may miss the rate
    text = report(r, {"A": "SL V3", "B": "TL Wireless LCD, experimental"})
    assert f"A (SL V3): {r.steady['A'].sent} frames sent, {r.steady['A'].acked} acknowledged" in text
    assert "resident memory 50.0 MiB at the start, 50.0 MiB at the end" in text
    assert "B after its USB reset: 0." in text


def test_a_panel_that_reenumerates_is_opened_again(fakes: dict[str, list[Usb]]) -> None:
    def unplug(serial: str) -> None:
        def gone(data: bytearray, timeout_ms: int = 1000) -> None:
            raise OSError(errno.ENODEV, "No such device")

        fakes[serial][-1].write = gone  # type: ignore[method-assign]

    r = soak([slv3.Slv3("A")], FRAMES, 0.2, unplug, lambda: 0)
    assert r.recovery["A"] is not None
    assert r.after["A"].errors == {"[Errno 19] No such device": 1}
    assert len(fakes["A"]) == 3  # opened for the frames, for the reset, and again after it


def test_a_panel_that_stops_acknowledging_fails_and_says_so(fakes: dict[str, list[Usb]]) -> None:
    def hang(serial: str) -> None:
        fakes[serial][-1].read = lambda timeout_ms=1000: b""  # type: ignore[method-assign]

    memory = iter(range(0, 100 * 2**20, 10 * 2**20))
    r = soak([slv3.Slv3("A")], FRAMES, 0.2, hang, lambda: next(memory), limit=0.2)
    assert r.recovery == {"A": None}
    found = problems(r)
    assert "A: no frame acknowledged after its reset" in found
    assert any(p.startswith("resident memory grew") for p in found)
    assert "A after its USB reset: no acknowledged frame" in report(r, {"A": "SL V3"})


def test_holders_names_the_other_programs_with_a_panel_open(tmp_path: Path) -> None:
    for pid, name, target in ((1234, "pixdial", "/dev/bus/usb/001/004"), (99, "bash", "/dev/pts/0")):
        (tmp_path / str(pid) / "fd").mkdir(parents=True)
        (tmp_path / str(pid) / "comm").write_text(name + "\n")
        (tmp_path / str(pid) / "fd" / "5").symlink_to(target)
    (tmp_path / str(os.getpid()) / "fd").mkdir(parents=True)
    (tmp_path / str(os.getpid()) / "fd" / "3").symlink_to("/dev/bus/usb/001/005")  # this test itself
    nodes = {"/dev/bus/usb/001/004", "/dev/bus/usb/001/005"}
    assert holders(nodes, tmp_path) == ["1234 (pixdial) /dev/bus/usb/001/004"]
