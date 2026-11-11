# Changelog

All notable changes are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added Python 3.14 to CI and package classifiers.
- Added a tag-triggered release workflow with version checks, PyPI attestations and GitHub releases from the changelog.
- Added bug, device request, device test and Radeon issue forms, with questions directed to Discussions.
- Added a pull request template for hardware-test notes and an issue label and triage guide.
- Added the Contributor Covenant 2.1 code of conduct with reporting through GitHub.
- Added systemd user units to the AUR and Nix packages, with package-specific paths and no restart on config errors.

### Changed

- Prepared AUR and Nix recipes for 0.1.1, with explicit placeholders for the unpublished sdist URL and checksums.
- Documented tag-triggered releases, Trusted Publishing setup and package updates after publication.

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
