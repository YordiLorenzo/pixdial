"""The SL V3 protocol: header bytes against a capture, the brightness curve, and what a panel is sent."""

from __future__ import annotations

import ctypes
import errno
import functools
import io
from pathlib import Path

import pytest
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from PIL import Image

from pixdial.devices import slv3, usbfs

CAPTURE = Path(__file__).parent / "data" / "slv3-headers.txt"
SENT_IN_NORMAL_USE = {slv3.REVISION, slv3.FRAME_RATE, slv3.VERSION, slv3.BRIGHTNESS, slv3.FRAME}


def captured() -> list[tuple[int, int, bytes, bool, bytes]]:
    rows = []
    for line in CAPTURE.read_text().splitlines():
        if not line.startswith("#"):
            command, stamp, params, winusb, header = line.split()
            params_ = b"" if params == "-" else bytes.fromhex(params)
            rows.append((int(command, 16), int(stamp), params_, winusb == "1", bytes.fromhex(header)))
    return rows


def plain(header: bytes) -> bytes:
    """A header decrypted, padding included."""
    winusb = header[510:] == b"\xa1\x1a"
    des = Cipher(TripleDES(slv3.KEY * 3), modes.CBC(slv3.KEY)).decryptor()
    return des.update(header[:504] if winusb else header) + des.finalize()


@pytest.mark.parametrize(("command", "stamp", "params", "winusb", "expected"), captured())
def test_header_matches_the_capture(command: int, stamp: int, params: bytes, winusb: bool, expected: bytes) -> None:
    assert slv3.header(command, stamp, params, winusb) == expected


def test_header_layout() -> None:
    p = plain(slv3.header(0x65, 100_001, (0x12345).to_bytes(4, "big")))
    assert p[:8] == bytes([0x65, 0, 0x1A, 0x6D]) + (100_001).to_bytes(4, "little")
    assert p[8:12] == bytes([0, 1, 0x23, 0x45])
    assert p[12:504] == bytes(492)
    assert p[504:] == bytes([8]) * 8  # PKCS7


def test_winusb_header_has_its_trailer() -> None:
    header = slv3.header(0x80, 5, winusb=True)
    assert len(header) == 512
    assert header[504:] == bytes(6) + b"\xa1\x1a"
    assert plain(header)[:500] == bytes([0x80, 0, 0x1A, 0x6D]) + (5).to_bytes(4, "little") + bytes(492)


@pytest.mark.parametrize(
    ("percent", "level"), [(0, 0), (25, 10), (50, 30), (75, 40), (100, 100), (37, 20), (62, 35), (200, 100)]
)
def test_brightness_follows_the_firmware_curve(percent: int, level: int) -> None:
    assert slv3.brightness_level(percent) == level


def test_stamps_only_rise() -> None:
    times = iter([10.0, 10.0, 10.0, 10.5, 10.2])
    stamps = slv3.Stamps(lambda: next(times))
    assert [stamps.next() for _ in range(4)] == [1, 2, 500, 501]


def test_jpeg_fits_one_transfer_and_turns() -> None:
    image = Image.new("RGB", (400, 400))
    image.putpixel((0, 0), (255, 255, 255))
    data = slv3.jpeg(image, 180)
    assert len(data) <= slv3.PACKET - slv3.HEADER
    with Image.open(io.BytesIO(data)) as turned:
        assert turned.convert("L").getpixel((399, 399)) == pytest.approx(255, abs=60)  # top left went to bottom right


class Usb:
    """A panel that acknowledges every command and answers the version query."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.replies: list[bytes] = []
        self.closed = False

    def write(self, data: bytearray, timeout_ms: int = 1000) -> None:
        self.sent.append(bytes(data))

    def read(self, timeout_ms: int = 1000) -> bytes:
        last = plain(self.sent[-1][: slv3.HEADER])[0]
        reply = bytes([last]) + bytes(7) + (b"slv3_2024091003_01\0" if last == slv3.VERSION else b"")
        self.replies.append(reply)
        return reply

    def close(self) -> None:
        self.closed = True

    def commands(self) -> list[int]:
        return [plain(data[: slv3.HEADER])[0] for data in self.sent]


@pytest.fixture
def usb(monkeypatch: pytest.MonkeyPatch) -> Usb:
    fake = Usb()
    monkeypatch.setattr(slv3, "connect", lambda serial: fake)
    return fake


def test_open_sends_the_daemons_start_up(usb: Usb) -> None:
    panel = slv3.Slv3("abc", brightness=75)
    assert panel.open() == "firmware slv3_2024091003_01"
    assert usb.commands() == [slv3.REVISION, slv3.FRAME_RATE, slv3.VERSION, slv3.BRIGHTNESS]
    assert plain(usb.sent[1])[8] == 120  # the frame rate the daemon always sets
    assert plain(usb.sent[3])[8] == 40  # 75 % on the firmware's curve


def test_a_frame_is_one_padded_transfer(usb: Usb) -> None:
    panel = slv3.Slv3("abc", turn=180)
    panel.open()
    image = Image.new("RGB", (400, 400), (200, 100, 50))
    panel.show(image)
    frame = usb.sent[-1]
    size = int.from_bytes(plain(frame[: slv3.HEADER])[8:12], "big")
    assert len(frame) == slv3.PACKET
    assert frame[slv3.HEADER : slv3.HEADER + size] == slv3.jpeg(image, 180)
    assert frame[slv3.HEADER + size :] == bytes(slv3.PACKET - slv3.HEADER - size)


def test_a_frames_acknowledgement_is_read_before_the_next_command(usb: Usb) -> None:
    panel = slv3.Slv3("abc")
    panel.open()
    reads = len(usb.replies)
    panel.show(Image.new("RGB", (400, 400)))
    assert len(usb.replies) == reads  # not waited for
    panel.show(Image.new("RGB", (400, 400)))
    assert len(usb.replies) == reads + 1


def test_only_the_commands_of_normal_use_are_sent(usb: Usb) -> None:
    panel = slv3.Slv3("abc")
    panel.open()
    panel.show(Image.new("RGB", (400, 400)))
    panel.off()
    panel.close()
    assert set(usb.commands()) <= SENT_IN_NORMAL_USE
    assert usb.commands()[-1] == slv3.BRIGHTNESS and plain(usb.sent[-1])[8] == 0
    stamps = [int.from_bytes(plain(data[: slv3.HEADER])[4:8], "little") for data in usb.sent]
    assert stamps == sorted(set(stamps))
    assert usb.closed


def usb_device(sysfs: Path, port: str, product: str, serial: str, devnum: int) -> None:
    d = sysfs / port
    d.mkdir(parents=True)
    for name, text in {"idVendor": "1cbe", "idProduct": product, "busnum": "1", "devnum": str(devnum)}.items():
        (d / name).write_text(text + "\n")
    (d / "serial").write_text(serial + "\n")


@pytest.fixture
def sysfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """/sys/bus/usb/devices with an SL V3 LCD, a TL LCD and a HydroShift II LCD Circle (1cbe:a021, another
    protocol), and a hub interface directory that has no ids."""
    root = tmp_path / "usb"
    usb_device(root, "1-2", "0005", "SLV3SERIAL", 4)
    usb_device(root, "1-3", "0006", "TLSERIAL", 5)
    usb_device(root, "1-4", "a021", "AIOSERIAL", 6)
    (root / "1-0:1.0").mkdir()
    monkeypatch.setattr(slv3, "attached", functools.partial(usbfs.attached, sysfs=root))
    return root


def test_a_tl_lcd_is_found_as_experimental_and_driven_like_an_sl_v3(
    sysfs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = slv3.Slv3.discover()
    assert [(f.id, f.where, f.note) for f in found] == [
        ("SLV3SERIAL", "usb 1-2 (/dev/bus/usb/001/004)", ""),
        ("TLSERIAL", "usb 1-3 (/dev/bus/usb/001/005)", "TL Wireless LCD, experimental"),
    ]
    fake, opened = Usb(), []

    def bulk(node: str, out_ep: int, in_ep: int) -> Usb:
        opened.append((node, out_ep, in_ep))
        return fake

    monkeypatch.setattr(slv3, "Bulk", bulk)
    panel = slv3.Slv3("TLSERIAL")
    assert panel.problem() == f"no read and write access to usb 1-3 (/dev/bus/usb/001/005) ({slv3.UDEV_RULE} gives it)"
    assert panel.open() == "firmware slv3_2024091003_01"
    panel.show(Image.new("RGB", (400, 400)))
    assert opened == [("/dev/bus/usb/001/005", slv3.EP_OUT, slv3.EP_IN)]
    assert fake.commands() == [slv3.REVISION, slv3.FRAME_RATE, slv3.VERSION, slv3.BRIGHTNESS, slv3.FRAME]
    assert slv3.Slv3("AIOSERIAL").problem() == "no SL V3 or TL LCD with serial AIOSERIAL attached"
    with pytest.raises(FileNotFoundError, match="AIOSERIAL"):
        slv3.Slv3("AIOSERIAL").open()


def test_the_udev_rule_covers_every_product_the_driver_opens() -> None:
    rules = [line for line in slv3.UDEV_RULE.read_text().splitlines() if line and not line.startswith("#")]
    assert rules == [
        f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{slv3.VENDOR:04x}", ATTRS{{idProduct}}=="{product:04x}", TAG+="uaccess"'
        for product in slv3.PRODUCTS
    ]


def test_options_are_checked() -> None:
    with pytest.raises(ValueError, match="turn"):
        slv3.Slv3("abc", turn=45)
    with pytest.raises(ValueError, match="brightness"):
        slv3.Slv3("abc", brightness=101)


def test_a_write_goes_out_in_16_kb_pieces_with_the_same_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    pieces: list[bytes] = []

    def ioctl(fd: int, request: int, transfer: usbfs._Bulk) -> int:
        assert request == usbfs.USBDEVFS_BULK and transfer.ep == slv3.EP_OUT
        pieces.append(ctypes.string_at(transfer.data, transfer.len))
        return int(transfer.len)

    monkeypatch.setattr("pixdial.devices.usbfs.fcntl.ioctl", ioctl)
    bulk = object.__new__(usbfs.Bulk)
    bulk.fd, bulk.out_ep, bulk.in_ep = -1, slv3.EP_OUT, slv3.EP_IN
    _, _, params, _, header = next(row for row in captured() if row[0] == slv3.FRAME)
    size = int.from_bytes(params, "big")
    packet = bytearray(
        header + bytes(range(256)) * (size // 256) + bytes(slv3.PACKET - slv3.HEADER - size // 256 * 256)
    )
    bulk.write(packet)
    assert b"".join(pieces) == packet
    assert [len(p) for p in pieces] == [16_384] * 6 + [4_096]  # whole 512-byte packets: none ends short
    pieces.clear()
    bulk.write(bytearray(header))
    assert pieces == [header]


def test_a_piece_refused_for_want_of_usbfs_memory_is_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    refusals, sent = [2], []

    def ioctl(fd: int, request: int, transfer: usbfs._Bulk) -> int:
        if refusals[0]:
            refusals[0] -= 1
            raise OSError(errno.ENOMEM, "Cannot allocate memory")
        sent.append(int(transfer.len))
        return int(transfer.len)

    clock = [0.0]
    monkeypatch.setattr("pixdial.devices.usbfs.fcntl.ioctl", ioctl)
    monkeypatch.setattr("pixdial.devices.usbfs.time.sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr("pixdial.devices.usbfs.time.monotonic", lambda: clock[0])
    bulk = object.__new__(usbfs.Bulk)
    bulk.fd, bulk.out_ep, bulk.in_ep = -1, slv3.EP_OUT, slv3.EP_IN
    bulk.write(bytearray(slv3.PACKET))
    assert sum(sent) == slv3.PACKET  # the refused piece was sent after all, so the frame went out whole
    refusals[0] = 1000
    with pytest.raises(OSError, match="Cannot allocate memory"):
        bulk.write(bytearray(512))  # refused for over half a second: given up, and the screen reopens the panel
