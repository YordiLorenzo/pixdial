"""Lian Li UNI FAN SL V3 Wireless LCD (USB 1cbe:0005): a round 400 x 400 panel that shows JPEG frames.

The protocol, as lian-li-linux's daemon speaks it (lianli-devices slv3_lcd.rs and crypto.rs, v1.2.4): every command
is a 512-byte header, DES-CBC encrypted with key and IV "slv3tuzx": the command, 0x1a 0x6d, a millisecond stamp that
only rises, the parameters. A frame is the header of command 0x65 with the JPEG's size, then the JPEG, zero-padded
to 102,400 bytes and written in 16 KB pieces (usbfs.Bulk), as the daemon's libusb transfer reaches the panel; the
panel acknowledges each command on the IN endpoint. This driver sends only what the daemon sends in normal use: its
start-up queries, frames and brightness. Never the reboot, rotate, startup image or storage commands, and nothing
that writes the panel's firmware.
"""

from __future__ import annotations

import io
import itertools
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from PIL import Image

from .base import Device, Found
from .usbfs import Bulk, attached

VENDOR, PRODUCT = 0x1CBE, 0x0005
KEY = b"slv3tuzx"  # DES key and IV of every 1cbe panel's headers
PACKET = 102_400  # header and JPEG, zero-padded: one frame
HEADER = 512
EP_OUT, EP_IN = 0x01, 0x81
REVISION, FRAME_RATE, VERSION, BRIGHTNESS, FRAME = 0x80, 0x0F, 0x0A, 0x0E, 0x65
BRIGHTNESS_CURVE = ((0, 0), (25, 10), (50, 30), (75, 40), (100, 100))  # the firmware's: percent -> level
UDEV_RULE = Path(__file__).parent.parent / "data" / "60-pixdial.rules"
TURNS = {0: None, 90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}


class Transport(Protocol):
    def write(self, data: bytearray, timeout_ms: int = 1000) -> None: ...
    def read(self, timeout_ms: int = 1000) -> bytes: ...
    def close(self) -> None: ...


def header(command: int, stamp: int, params: bytes = b"", winusb: bool = False) -> bytes:
    """A command's 512-byte header (PacketBuilder::build, or build_winusb: a 500-byte plaintext and a trailer)."""
    plain = bytearray(500 if winusb else 504)
    plain[0], plain[2:8] = command, b"\x1a\x6d" + stamp.to_bytes(4, "little")
    plain[8 : 8 + len(params)] = params
    pad = 8 - len(plain) % 8  # PKCS7
    des = Cipher(TripleDES(KEY * 3), modes.CBC(KEY)).encryptor()  # TripleDES with three equal keys is single DES
    sealed = des.update(bytes(plain) + bytes([pad]) * pad) + des.finalize()
    return sealed + bytes(6) + b"\xa1\x1a" if winusb else sealed


def brightness_level(percent: int) -> int:
    """The level the firmware takes for a brightness in percent (slv3_brightness_lut): linear between its points."""
    v = min(max(percent, 0), 100)
    (x0, y0), (x1, y1) = next(pair for pair in itertools.pairwise(BRIGHTNESS_CURVE) if v <= pair[1][0])
    return y0 + ((v - x0) * (y1 - y0) + (x1 - x0) // 2) // (x1 - x0)


def jpeg(image: Image.Image, turn: int) -> bytes:
    """The picture turned for the panel's mount (clockwise), as a JPEG that fits in a frame after its header:
    full-resolution colour keeps thin coloured lines sharp, and a busier picture steps the quality down."""
    transpose = TURNS[turn]
    turned = image.transpose(transpose) if transpose is not None else image
    for quality in (90, 80, 70, 55):
        out = io.BytesIO()
        turned.save(out, "JPEG", quality=quality, subsampling=0)
        if out.tell() <= PACKET - HEADER:
            return out.getvalue()
    raise ValueError(f"frame still {out.tell()} bytes at JPEG quality {quality}")


class Stamps:
    """Milliseconds since the panel was opened, never the same twice."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock, self.start, self.last = clock, clock(), 0

    def next(self) -> int:
        self.last = max(int((self.clock() - self.start) * 1000), self.last + 1) & 0xFFFFFFFF
        return self.last


def connect(serial: str) -> Bulk:
    for device in attached(VENDOR, PRODUCT):
        if device.serial == serial:
            return Bulk(device.node, EP_OUT, EP_IN)
    raise FileNotFoundError(f"no SL V3 LCD with serial {serial}")


class Slv3(Device):
    """One SL V3 LCD by its USB serial. turn: degrees each frame is turned clockwise for the fan's mount (0, 90, 180
    or 270); brightness: the backlight in percent."""

    usb: Transport  # set by open(), with stamps
    stamps: Stamps

    def __init__(self, serial: str, turn: int = 0, brightness: int = 100) -> None:
        if turn not in TURNS:
            raise ValueError(f"turn must be 0, 90, 180 or 270, not {turn!r}")
        if not 0 <= brightness <= 100:
            raise ValueError(f"brightness must be 0 to 100, not {brightness!r}")
        self.id = self.serial = serial
        self.turn, self.brightness = turn, brightness
        self.packet = bytearray(PACKET)
        self.pending = False  # a frame's acknowledgement not read yet

    @classmethod
    def discover(cls) -> list[Found]:
        return [
            Found(d.serial, f"usb {d.port} ({d.node})", os.access(d.node, os.R_OK | os.W_OK))
            for d in attached(VENDOR, PRODUCT)
        ]

    def problem(self) -> str | None:
        for found in self.discover():
            if found.id == self.serial:
                return None if found.access else f"no read and write access to {found.where} ({UDEV_RULE} gives it)"
        return f"no SL V3 LCD with serial {self.serial} attached"

    def open(self) -> str:
        """The daemon's start-up (Slv3LcdDevice::send_init): the revision query, the frame rate it always sets
        (120), the firmware version; then the brightness, which the daemon sets at 0 when it stops."""
        usb = self.usb = connect(self.serial)
        self.stamps, self.pending = Stamps(), False
        try:
            usb.write(bytearray(header(REVISION, self.stamps.next(), winusb=True)))
            usb.read(10)  # older panels don't answer
            usb.write(bytearray(header(FRAME_RATE, self.stamps.next(), bytes([120]))))
            usb.read()
            usb.write(bytearray(header(VERSION, self.stamps.next())))
            reply = usb.read()
            self.set_brightness(self.brightness)
        except OSError:
            usb.close()
            raise
        firmware = reply[8:].split(b"\0")[0].decode(errors="replace") if len(reply) > 8 else "?"
        return f"firmware {firmware}"

    def show(self, image: Image.Image) -> None:
        """One frame. The panel acknowledges it at its next 60 Hz refresh, about 14 ms after the 3 ms transfer, so
        the acknowledgement is read before the next command rather than waited for here."""
        data = jpeg(image, self.turn)
        self.settle()
        self.packet[:HEADER] = header(FRAME, self.stamps.next(), len(data).to_bytes(4, "big"))
        self.packet[HEADER : HEADER + len(data)] = data
        self.packet[HEADER + len(data) :] = bytes(PACKET - HEADER - len(data))
        self.usb.write(self.packet)
        self.pending = True

    def off(self) -> None:
        self.set_brightness(0)

    def close(self) -> None:
        self.usb.close()

    def set_brightness(self, percent: int) -> None:
        self.settle()
        self.usb.write(bytearray(header(BRIGHTNESS, self.stamps.next(), bytes([brightness_level(percent)]))))
        self.usb.read()

    def settle(self) -> None:
        if self.pending:
            self.pending = False
            self.usb.read()
