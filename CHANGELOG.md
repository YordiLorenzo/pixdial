# Changelog

All notable changes are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Experimental support for the Lian Li UNI FAN TL Wireless LCD (`1cbe:0006`) in the SL V3 driver, with its udev lines.
- Experimental `amdgpu` source, on by default: AMD GPU temperature, power, utilisation and VRAM, read without root.

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
