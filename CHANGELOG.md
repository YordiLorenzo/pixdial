# Changelog

All notable changes are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- The default layout and rotation leave out designs whose readings no source gives (psu without a PSU source, gpu without NVIDIA); `doctor` lists them.
- `pixdial service install`, `remove` and `status`: the bundled user unit with ExecStart pointed at the running pixdial.
- A config error (exit status 2) stops the service once instead of restarting it every 10 seconds.
- Text draws without libraqm: font features go to Pillow only when it has raqm, and `doctor` says whether it has.

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
