# Architecture

pixdial samples readings, gives each panel's design a shared snapshot, draws frames and sends changed frames to
the device. Designs contain no I/O; sources and devices handle it at either end.

| Area | Code | Responsibility |
| --- | --- | --- |
| Readings | `src/pixdial/readings.py` | Values, limits, snapshots and history trails |
| Extension points | `src/pixdial/designs/`, `sources/`, `devices/` | Drawing, sampling and frame transport |
| Runtime | `src/pixdial/runtime/` | Source threads, stale values, layout, rotation and frame scheduling |
| Configuration | `src/pixdial/config.py`, `plugins.py` | TOML validation, entry points and object construction |
| CLI and previews | `src/pixdial/cli.py`, `doctor.py`, `demo.py`, `gallery.py` | Commands, checks and synthetic preview readings |

## Frame lifecycle

1. The sampler reads each source in its own thread and drops stale values from the next snapshot.
2. A design's `update()` returns keys for its still and moving parts.
3. The screen redraws the still part only when its key changes, at most 10 times per second.
4. Motion is drawn over a copy at the design's frame rate, up to the runtime's 30 frames per second.
5. A changed frame goes to the device. An unchanged frame is resent after 30 seconds; switching designs blends
   over 0.4 seconds.

Failed device opens are retried after 10 seconds. A source failure does not stop other sources; a render failure
is reported for that panel. After resume, the runtime drops old readings, resets source handles and reopens devices.
Normal shutdown calls each open device's `off()` and `close()`.

## SL V3 transport

The driver follows the SL V3 protocol in
[sgtaziz/lian-li-linux](https://github.com/sgtaziz/lian-li-linux), daemon v1.2.4 (`slv3_lcd.rs`, `crypto.rs`).
Linux usbdevfs provides bulk transfers directly through the device node; libusb is not required.

Commands have a 512-byte DES-CBC header. The fixed protocol key is device compatibility data, not a user secret
or a security boundary. A frame contains the header and a JPEG, padded to 102,400 bytes and written in 16 KB pieces.
Host-side rotation and JPEG compression happen before transmission.

Startup queries the revision, sets the protocol's frame-rate field to 120, queries the firmware version and sets
brightness. The field value does not mean pixdial renders at 120 fps. Normal operation sends frames and brightness;
shutdown sets brightness to zero. It sends no reboot, panel-rotation, startup-image, storage or firmware-write
commands. `tests/test_slv3.py` checks the command headers, allowed command set and transport behaviour using fakes.
Those tests do not establish compatibility with other panel models.

## Files and network

Configuration is under `XDG_CONFIG_HOME`; the current layout is under `XDG_STATE_HOME`.
See [Configuration](config.md) for defaults and the interaction between config and saved selections.
`render` and file devices create local output at the selected paths. `pixdial service install` installs the
systemd user unit, as the user. `pixdial setup` installs the udev rule (and, on a machine where the service starts
with nobody logged in at it, the `pixdial` group with the user in it) through sudo, after it prints the commands.
Those commands are the only ones that run as root; pixdial itself runs as the user.

Built-in sensor readers use `/proc`, `/sys` or NVML without network requests. The runtime has no telemetry or
network listener. Command sources and Python plugins can run arbitrary code with the user's permissions,
including making network requests. `doctor` also invokes sources. See [Security](../SECURITY.md).
