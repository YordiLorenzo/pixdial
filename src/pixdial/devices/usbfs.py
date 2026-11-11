"""USB bulk transfers through Linux's usbdevfs: no libusb, just the device node and three ioctls."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path

SYSFS = Path("/sys/bus/usb/devices")
PROC = Path("/proc")
USBDEVFS_BULK = 0xC0185502
USBDEVFS_CLAIMINTERFACE = 0x8004550F
PIECE = 16_384  # bytes per bulk write: the pieces usbfs itself cuts the daemon's (libusb's) transfers into, USB_SG_SIZE


class _Bulk(ctypes.Structure):  # struct usbdevfs_bulktransfer
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint), ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


@dataclass(frozen=True)
class UsbDevice:
    serial: str
    node: str  # /dev/bus/usb/BBB/DDD
    port: str  # its sysfs name: bus-port.port


def attached(vendor: int, product: int, sysfs: Path = SYSFS) -> list[UsbDevice]:
    """The devices with this vendor and product id, by port."""
    found = []
    for d in sorted(sysfs.glob("*")):
        try:
            if (int(read(d / "idVendor"), 16), int(read(d / "idProduct"), 16)) != (vendor, product):
                continue
            node = f"/dev/bus/usb/{int(read(d / 'busnum')):03d}/{int(read(d / 'devnum')):03d}"
            found.append(UsbDevice(read(d / "serial"), node, d.name))
        except (OSError, ValueError):  # an interface directory, or a device without a serial
            continue
    return found


def products(vendor: int, sysfs: Path = SYSFS) -> list[tuple[int, str]]:
    """The product id and sysfs name of every attached device from this vendor."""
    found = []
    for d in sorted(sysfs.glob("*")):
        try:
            if int(read(d / "idVendor"), 16) == vendor:
                found.append((int(read(d / "idProduct"), 16), d.name))
        except (OSError, ValueError):  # an interface directory
            continue
    return found


def holder(device: UsbDevice, sysfs: Path = SYSFS, proc: Path = PROC) -> str:
    """What has claimed the device's interface 0, which a program must claim to talk to it (usbfs is then the
    interface's driver): "" while nothing has; the program of this user with the device open ("pixdial (pid 42)");
    else "a program of another user", whose open files this user can't see."""
    driver = sysfs / f"{device.port}:1.0" / "driver"  # configuration 1, interface 0
    if not driver.is_symlink() or driver.readlink().name != "usbfs":
        return ""
    for d in sorted(proc.glob("[0-9]*")):
        try:
            if any(str(fd.readlink()) == device.node for fd in (d / "fd").iterdir()):
                return f"{read(d / 'comm')} (pid {d.name})"
        except OSError:  # another user's, or gone
            continue
    return "a program of another user"


def read(path: Path) -> str:
    return path.read_text().strip()


class Bulk:
    """One USB device's interface 0, claimed for this process (EBUSY while another program has it), and its bulk
    endpoints."""

    def __init__(self, node: str, out_ep: int, in_ep: int) -> None:
        self.out_ep, self.in_ep = out_ep, in_ep
        self.fd = os.open(node, os.O_RDWR)
        try:
            fcntl.ioctl(self.fd, USBDEVFS_CLAIMINTERFACE, struct.pack("I", 0))
        except OSError:
            os.close(self.fd)
            raise
        self.reply = ctypes.create_string_buffer(512)

    def write(self, data: bytearray, timeout_ms: int = 1000) -> None:
        """data in pieces of at most 16 KB, one after another: the same 512-byte packets on the wire as one transfer
        (every piece but the last is a whole number of packets, so none ends short). usbfs copies each transfer
        through one block of kernel memory; 100 KB at once could not always be found while memory was fragmented
        (ENOMEM), 16 KB always can."""
        buf = (ctypes.c_char * len(data)).from_buffer(data)
        start = ctypes.addressof(buf)
        for offset in range(0, len(data), PIECE):
            self.bulk(_Bulk(self.out_ep, min(PIECE, len(data) - offset), timeout_ms, start + offset))

    def read(self, timeout_ms: int = 1000) -> bytes:
        """A reply of up to 512 bytes; empty when none came in time."""
        try:
            n = self.bulk(_Bulk(self.in_ep, 512, timeout_ms, ctypes.addressof(self.reply)))
        except TimeoutError:
            return b""
        return self.reply.raw[:n]

    def bulk(self, transfer: _Bulk) -> int:
        """One transfer. usbfs charges it to an allowance every program using usbfs shares (16 MB), which another one
        can use up for a moment: then it fails with ENOMEM before sending anything, and is tried again for up to half
        a second, so a frame begun in pieces is finished rather than left half sent."""
        deadline = time.monotonic() + 0.5
        while True:
            try:
                return int(fcntl.ioctl(self.fd, USBDEVFS_BULK, transfer))
            except OSError as error:
                if error.errno != errno.ENOMEM or time.monotonic() > deadline:
                    raise
            time.sleep(0.01)

    def close(self) -> None:
        os.close(self.fd)  # releases the interface
