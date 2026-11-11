# Changelog

All notable changes are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `pixdial run --debug` logs each USB command with its length and its acknowledgement time, and a traceback for each
  error.
- `pixdial run --log-file PATH` writes the log to a file, with the time on each line.
- `run` logs its panels and sources as it starts. Errors are logged as warnings, the rest as info.

### Fixed

- A frame too big for one SL V3 transfer is sent with 4:2:0 colour, instead of stopping the runtime.
- A device error other than `OSError` in `show()` is reported for that panel only; the other panels go on.
- A plugin design that fails in `__init__` is skipped for that panel, instead of stopping the runtime.
- A list value on a trail key (`cpu_load`, `psu_w`) leaves a gap in the trail, instead of stopping the runtime.
- Each panel sends its frames from a thread of its own, so a hung panel no longer slows the others to 1 frame/s.
- After a failed send, a panel is opened again after a wait that doubles from 0.2 s to 10 s, not at once, and the
  error is logged once, not once per frame.
- A panel that is unplugged, or not back yet after a resume, is tried again with the same doubling wait, not every
  10 s, so it is back within about a second of its return.
- A source read under way as the machine went to sleep no longer brings back a reading from before the sleep.

## [0.1.0] - 2026-11-06

### Added

- Initial 0.1.0 implementation: a Python SDK and CLI for hardware screens on Linux.
- Fourteen designs, warm/ember/ice themes, animated designs, history trails and transitions.
- Linux USB support for Lian Li UNI FAN SL V3 Wireless LCD panels (`1cbe:0005`), plus a PNG device for previews.
- CPU, RAPL, NVML, hwmon and command sources, with hardware-reported limits, config overrides and stale readings.
- `run`, `show`, `list`, `devices`, `render` and `doctor` commands, with TOML configuration and Python entry points
  for designs, sources and devices.

### Changed

- Expanded the README with a render gallery, theme samples and animation, with a reproducible image script.
- Moved detailed configuration and API documentation into guides; added contribution and security policies.
- Prepared GPL-3.0-or-later package metadata and licence; bundled Lato fonts retain their SIL Open Font License.
- Added CI for Ruff, mypy and pytest on Ubuntu with Python 3.12 and 3.13.

[Unreleased]: https://github.com/YordiLorenzo/pixdial/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YordiLorenzo/pixdial/releases/tag/v0.1.0
