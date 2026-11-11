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
- Experimental support for the Lian Li UNI FAN TL Wireless LCD (`1cbe:0006`) in the SL V3 driver, with its udev lines.
- Experimental `amdgpu` source, on by default: AMD GPU temperature, power, utilisation and VRAM, read without root.
- `pytest -m hardware`: an opt-in test on real panels (frame acknowledgements, 30 frames/s, CPU, memory, a USB
  reset), left out of the normal run.

### Changed

- Prepared AUR and Nix recipes for 0.1.1, with explicit placeholders for the unpublished sdist URL and checksums.
- Documented tag-triggered releases, Trusted Publishing setup and package updates after publication.
- `pixdial setup`: finds the panels, gives this user access (it prints the udev commands, then runs them through sudo), writes the config with a layout, and runs the doctor checks. On a machine that lingers or has no login at its seat, it installs a group rule and adds the user to the `pixdial` group. `--dry-run` writes and runs nothing.
- `service install` says when a headless machine needs the group rule from `setup`.
- `doctor --share`: a Markdown report for issues (versions, distro, kernel, USB ids, panel firmware, sources, hwmon chips, the readings each design misses), with serials, the hostname and the home folder taken out.
- `doctor` shows a default source that is missing as "skip" with a hint, and exits 0; with no panels in the config it lists the attached ones and prints a config for them.
- `doctor` and `devices` name the program that holds a panel, and point to lian-li-linux when another program has claimed it.
- `doctor` prints the installed version and the command that upgrades it.
- `devices` names the USB cable when it finds no panel, and points other Lian Li ids to lian-li-linux and Turing or TURZX ids to turing-smart-screen-python.
- The default layout and rotation leave out designs whose readings no source gives (psu without a PSU source, gpu without NVIDIA); `doctor` lists them.
- Plugin API: a design can declare `reads` and `needs`, and a source can say what it `gives()`.
- `pixdial service install`, `remove` and `status`: the bundled user unit with ExecStart pointed at the running pixdial.
- A config error (exit status 2) stops the service once instead of restarting it every 10 seconds.
- Text draws without libraqm: font features go to Pillow only when it has raqm, and `doctor` says whether it has.
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
- After a failed send, a panel is opened again after a wait that doubles from 0.25 s to 10 s, not at once, and the
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
