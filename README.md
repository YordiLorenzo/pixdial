<p align="center">
  <img src="docs/images/banner.png" width="100%" alt="pixdial: Beautiful hardware dashboards. Yours to build. A Python SDK and CLI for hardware screens on Linux.">
</p>

<p align="center">
  <a href="https://github.com/YordiLorenzo/pixdial/actions/workflows/ci.yml"><img src="https://github.com/YordiLorenzo/pixdial/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/pixdial/"><img src="https://img.shields.io/pypi/v/pixdial?color=FF9632" alt="PyPI version"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12%2B-FFDAB2" alt="Python 3.12 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-GPL--3.0--or--later-FF9632" alt="GPL-3.0-or-later"></a>
</p>

**pixdial puts live hardware readings on the LCDs in your PC, with a Python SDK to build your own designs.**

Pick from 14 designs for CPU load, temperatures, power, a clock and more. Match them to your build with three
themes, or write a design of your own. pixdial draws each frame on the host and sends it over USB.

[Website](https://yordilorenzo.github.io/pixdial/) · [Quick start](#quick-start) · [Supported hardware](#supported-hardware) · [Build a design](#build-a-design)

![All 14 built-in designs in the warm theme, rendered with demo readings](docs/images/designs.png)

## Quick start

You need Linux, Python 3.12 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), and a
[supported panel](#supported-hardware). For a preview without hardware, install pixdial and run
`pixdial render crown --state busy --out preview`.

1. **Install.**

   ```sh
   uv tool install pixdial
   ```

   `pipx install pixdial` works too. If your shell cannot find `pixdial`, run `uv tool update-shell` and open a
   new terminal.

2. **Give your user access to the panel.** On Linux with udev and an active local login, install the
   [bundled rule](src/pixdial/data/60-pixdial.rules):

   ```sh
   sudo tee /etc/udev/rules.d/60-pixdial.rules >/dev/null <<'RULE'
   SUBSYSTEM=="usb", ATTRS{idVendor}=="1cbe", ATTRS{idProduct}=="0005", TAG+="uaccess"
   RULE
   sudo udevadm control --reload-rules
   sudo udevadm trigger --subsystem-match=usb --action=add
   pixdial devices
   ```

   The rule grants access to this USB model. For a server without a local login, use a group rule as described
   in [Configuration](docs/config.md#usb-permissions). Run pixdial as your normal user.

3. **Configure one panel.** Create `~/.config/pixdial/config.toml` (or `$XDG_CONFIG_HOME/pixdial/config.toml`).
   Replace `YOUR_PANEL_SERIAL` with the value from `pixdial devices`.

   ```toml
   layout = ["crown"]

   [[panels]]
   name = "cpu"
   serial = "YOUR_PANEL_SERIAL"
   ```

   Add one `[[panels]]` table and one layout entry for each extra panel. Set `turn = 180` inside a panel's
   table if its display is upside down.

4. **Check the readings and start.**

   ```sh
   pixdial doctor
   pixdial run
   ```

   `doctor` checks panel permissions and reads each source. An unavailable source leaves its readings missing;
   the others keep working. Ctrl-C stops `run` and turns the connected panels dark.

In another terminal, `pixdial show crown:ember` changes the configured panel's design and theme.
`pixdial show rotate` cycles through the designs.

## What it does

### Designs that fit the screen

- **Fourteen round layouts.** Gauges, thread grids, power history, temperature rings and a clock, with type fitted
  to the panel.
- **Three themes.** `warm`, `ember` and `ice`, selected per panel. Changing designs fades between them;
  animated designs run at up to 30 frames per second.
- **Readable when a sensor goes away.** Missing or stale measurements show a dash instead of a frozen number.

![The crown design in warm, ember and ice, with the same demo readings](docs/images/themes.png)

<p align="center"><img src="docs/images/demo.webp" width="320" alt="The orb design animating CPU load and temperature from demo readings"></p>

### Readings with useful scales

- **Limits from the hardware.** Gauges use reported sensor limits, GPU power limits and slowdown temperatures
  when available. [Config overrides and fallback ranges](docs/config.md#readings-and-ranges) cover the rest.
- **Local sensors and your own data.** CPU load and power, NVIDIA GPU readings and Linux hardware sensors are built in.
  Add PSU readings, connector currents or agent quota through configured sensors, a command that prints JSON,
  or a Python source.

### Make it yours

- **Python plugins.** Add a design, source or device without changing pixdial. The runtime handles sampling,
  layout changes and frame delivery.
- **Preview before connecting.** Render PNGs and an HTML gallery from demo readings, or use the PNG device to
  try a live layout without a physical panel.

## Supported hardware

| Panel | USB ID | Display | OS |
| --- | --- | --- | --- |
| Lian Li UNI FAN SL V3 Wireless LCD | `1cbe:0005` | Round, 400 × 400 | Linux |

This is the only supported physical device today. Other Lian Li LCDs and AIO screens need their own tested
[device plugins](docs/plugins.md#devices). Despite the fan's name, its LCD receives frames over USB.
pixdial does not control fan speed or RGB lighting.

## CLI

| Command | Use |
| --- | --- |
| `pixdial run` | Run the configured panels until Ctrl-C or SIGTERM. |
| `pixdial show crown:ember` | Set one design per configured panel; `show` alone prints the selection, `show rotate` cycles designs. |
| `pixdial list` | List designs, themes, sources and devices, including installed plugins. |
| `pixdial devices` | Find attached panels and check access. |
| `pixdial render crown --out preview` | Render a PNG from demo readings; `render --gallery preview` builds the full gallery. |
| `pixdial doctor` | Check config, fonts, plugins, panel permissions, layout and source readings. |

Put `--config PATH` before the command to use another TOML file. Render states are `idle`, `busy`, `waiting`,
`full` and `missing`; `--scale 2` produces an 800 × 800 image. Exit codes are 0 for success, 1 for a failed check
or no devices found, and 2 for a usage or config error.

[Configuration](docs/config.md) covers multiple panels, sources, rotation and running at login.

## Build a design

A design turns a snapshot into a picture. Save this as `demo.py` in a [source checkout](#development), then
run `uv run python demo.py` to write `demo.png`:

```python
from pixdial.designs import LOAD, THEMES, Design
from pixdial.readings import Reading, Snapshot


class Load(Design):
    name = "load"
    shows = "CPU load on a gauge"

    def update(self, readings, now, dt):
        self.value = readings.number("cpu_load")
        return self.value, None

    def still(self):
        frame = self.frame(self.colour(LOAD, self.value))
        self.gauge(frame, self.value, LOAD)
        self.label(frame, "CPU LOAD")
        frame.number(246, self.value, "%")
        return frame.finish()


design = Load(THEMES["warm"])
design.update(Snapshot({"cpu_load": Reading(42, "%")}, wall=0), now=0, dt=0)
design.render(now=0).save("demo.png")
```

Register the class through the `pixdial.designs` entry-point group to use it by name in the CLI.
[The plugin guide](docs/plugins.md) covers registration, animation, history and all three extension points.
[examples/plugin](examples/plugin/) is a complete installable plugin with a design, source and device.

## What pixdial touches

The SL V3 driver talks to the panel over USB. It sends revision and version queries, frame-rate setup, JPEG
frames and brightness. It never sends firmware-write, reboot, panel-rotation, startup-image or storage commands.
The `turn` option rotates the image on the host. Stopping normally sets the panel's brightness to zero.

Built-in sensor readers read local files or NVML. pixdial has no telemetry or network service. A command source
or installed plugin can use the network and has your user's permissions; only configure code you trust.
`doctor` reads sources too, so it can execute configured commands.

`show` saves the layout in `$XDG_STATE_HOME/pixdial/layout` (default `~/.local/state/pixdial/layout`).
`render` writes to its output directory; file devices write to the paths you configure.
See [Architecture](docs/architecture.md) and [Security](SECURITY.md) for the boundaries.

## Credits and alternatives

[sgtaziz/lian-li-linux](https://github.com/sgtaziz/lian-li-linux) already supports these screens on Linux, with
presets, templates and a layout editor, under the MIT licence. pixdial's SL V3 protocol implementation follows
its daemon's `slv3_lcd.rs` and `crypto.rs` at v1.2.4. Choose it if you want to build layouts in an editor;
pixdial focuses on its supplied designs, hardware-derived ranges and Python plugins.

Rendering uses [Pillow](https://python-pillow.org/) and [NumPy](https://numpy.org/), with
[cryptography](https://cryptography.io/) for the panel's command headers. The bundled
[Lato fonts](https://www.latofonts.com/) by Łukasz Dziedzic retain their
[SIL Open Font License](src/pixdial/fonts/LICENSE-Lato.txt).

pixdial is not affiliated with Lian Li or the hardware manufacturers named here.

## FAQ

### Can I try it without a panel?

Yes. `pixdial render crown --out preview` needs no hardware. For a running layout, use the
[PNG device example](docs/config.md#try-a-live-layout-without-hardware). Rendering also works on macOS;
physical panel support is Linux-only.

### Why are some values missing?

The default sources read CPU load, RAPL package power, NVIDIA GPU readings and CPU temperature via hwmon.
Availability depends on your hardware, drivers and file permissions. PSU readings, connector currents and agent
quota need [additional sources](docs/config.md#sources). `pixdial doctor` shows what each source can read.

### Can I run it alongside lian-li-linux?

Use only one program per panel. Remove the panels pixdial drives from the other daemon's configuration;
otherwise the programs compete for the USB interface.

### Does it need root?

The panel needs read and write access to its USB device node. The udev rule in the quick start grants that to
the locally logged-in user. RAPL counters can need separate read permission. pixdial itself runs as your user.

## Development

```sh
git clone https://github.com/YordiLorenzo/pixdial.git
cd pixdial
uv sync --locked
uv run ruff check
uv run mypy
uv run pytest -q
```

[CONTRIBUTING.md](CONTRIBUTING.md) covers golden images, rebuilding the graphics and adding designs, sources
or devices. [Architecture](docs/architecture.md) maps the code; [CHANGELOG.md](CHANGELOG.md) tracks changes.
Report vulnerabilities privately through [SECURITY.md](SECURITY.md).

## Licence

pixdial is free software under the [GNU General Public License, version 3 or later](LICENSE)
(`GPL-3.0-or-later`). You may use, modify and redistribute it, including commercially, under those terms.
Bundled fonts keep their own licence as credited above.
