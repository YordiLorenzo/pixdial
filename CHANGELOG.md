# Changelog

All notable changes are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-11-11

### Added

- `pixdial setup` finds the panels, gives your user access to them, writes the config and runs the `doctor`
  checks. It prints the udev commands, then runs them through sudo, which asks for your password once. On a machine
  that starts pixdial with nobody logged in, it installs a group rule and adds you to the `pixdial` group.
  `--dry-run` changes nothing.
- `pixdial service install`, `remove` and `status` run `pixdial run` at every login as a systemd user service,
  pointed at the pixdial you installed.
- `pixdial doctor --share` prints a Markdown report for an issue, with panel serials, the hostname and your home
  folder taken out.
- `pixdial run --debug` logs each USB command, its acknowledgement time and a traceback for each error.
  `--log-file PATH` writes the log to a file.
- Experimental support for the Lian Li UNI FAN TL Wireless LCD (TL V2, `1cbe:0006`), with its udev lines. It uses
  the SL V3 protocol; no TL panel has been tested with pixdial yet.
- An experimental `amdgpu` source, on by default: AMD GPU temperature, power, utilisation and VRAM, read without
  root. On a processor's built-in GPU it leaves out power, which there includes the CPU.
- Python 3.14 support.
- Systemd user units in the AUR and Nix packages.
- Issue forms for bugs, device requests, device tests and Radeon reports, a pull request template and a code of
  conduct.
- `pytest -m hardware`, an opt-in test on real panels: frame acknowledgements at 30 frames/s, CPU, memory and a
  USB reset.
- Plugin API: a design can declare the readings it `reads` and `needs`, and a source can say what it `gives()`.
- A release workflow that publishes tagged versions to PyPI with attestations.

### Changed

- `doctor` shows a missing default source as "skip" with a hint, and exits 0. With no panels in the config, it
  lists the attached panels and prints a config for them.
- `doctor` and `devices` name the program that holds a panel, and point to lian-li-linux when it is another
  program.
- `doctor` prints the installed version and the command that upgrades it.
- `devices` names the USB cable when it finds no panel. It points other Lian Li devices to lian-li-linux, and
  Turing and TURZX screens to turing-smart-screen-python.
- The default layout and rotation leave out designs whose readings no source gives, such as psu without a PSU
  source. `doctor` lists them.
- `run` logs its panels and sources as it starts, and logs errors as warnings.
- The README and website set up with `pixdial setup` and `pixdial service install`, and add troubleshooting and
  undo steps. The PyPI summary names the fan as Lian Li UNI FAN SL Wireless LCD (SL V3).
- The protocol credit points to lian-li-linux v1.2.6, whose SL V3 code is unchanged since v1.2.4.

### Fixed

- One panel's problem no longer stops every panel. Each of these used to stop the runtime and turn all panels
  dark; now it stays with its own panel:
  - a frame too big for one SL V3 transfer: it is sent with 4:2:0 colour;
  - a device error other than `OSError` while showing a frame: it is logged for that panel, and the others go on;
  - a plugin design that fails as it starts: it is skipped, and the panel keeps the design it shows;
  - a list value on a trail key (`cpu_load`, `psu_w`): it leaves a gap in the trail.
- A hung panel no longer slows the other panels to 1 frame/s: each panel sends its frames from its own thread.
- After a failed send, pixdial opens the panel again after a wait that doubles from 0.25 s to 10 s, and logs the
  error once, not once per frame.
- A panel that is unplugged, or not back yet after a resume, comes back within about a second of its return,
  not after up to 10 s.
- A source read under way as the machine went to sleep no longer brings back a reading from before the sleep.
- A config error (exit status 2) stops the service once, instead of restarting it every 10 seconds.
- Text draws on a Pillow without raqm (for example without FriBiDi installed), where it failed before; `doctor`
  says whether Pillow has raqm.

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

[Unreleased]: https://github.com/YordiLorenzo/pixdial/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/YordiLorenzo/pixdial/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/YordiLorenzo/pixdial/releases/tag/v0.1.0
