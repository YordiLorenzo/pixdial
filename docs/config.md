# Configuration

pixdial reads `~/.config/pixdial/config.toml`, or `$XDG_CONFIG_HOME/pixdial/config.toml` when set.
Use `pixdial --config PATH COMMAND` to choose another file. An explicit path must exist.

## Panels and layouts

This Linux example needs two supported panels. Replace the serial placeholders with the values from
`pixdial devices`:

```toml
theme = "warm"
layout = ["crown", "gpu:ice"]
rotate_every = 60
rotation = ["crown", "gpu", "clock"]

[[panels]]
name = "cpu"
serial = "FIRST_PANEL_SERIAL"
turn = 180
brightness = 75

[[panels]]
name = "gpu"
serial = "SECOND_PANEL_SERIAL"
```

| Key | Meaning and default |
| --- | --- |
| `theme` | `warm`, `ember` or `ice`; default `warm`. A `name:theme` layout entry overrides it. |
| `layout` | One design per panel, in panel order, or `"rotate"`. Defaults to the first designs in `pixdial list`. |
| `rotate_every` | Seconds before the next design in rotation; positive, default 60. |
| `rotation` | Design names to cycle through. Empty or omitted means every available design. |
| `panels` | One table per panel. `run` requires at least one. |

A panel's `name` identifies it in log messages and must be unique. It defaults to its position, starting at `1`.
`device` defaults to `slv3`; the remaining keys go to that device's constructor.
For `slv3`, `serial` is required, `turn` is 0, 90, 180 or 270 degrees clockwise (default 0), and `brightness`
is 0 to 100 (default 100). Rotation happens on the host before JPEG encoding.

For the two-panel config above:

```sh
pixdial show crown gpu:ice
pixdial show rotate
pixdial show
```

`show` writes a selection even if `run` is stopped. The selection survives a restart and takes precedence over
`layout` in the config. It lives at `$XDG_STATE_HOME/pixdial/layout`, defaulting to
`~/.local/state/pixdial/layout`. Different `--config` files share this state unless you also set a different
`XDG_STATE_HOME`. To select a new fixed layout, use `show` with one design per panel.

## USB permissions

Linux needs read and write access to the panel's node under `/dev/bus/usb/`. The
[quick start](../README.md#quick-start) installs the bundled `uaccess` rule for a local login.
`pixdial devices` lists the serial and access status; `pixdial doctor` checks the configured panels without
opening them.

On a server without an active local login, an administrator can instead use a dedicated group. The following
Linux-only commands create `pixdial` if needed, add your user and install a group rule:

```sh
getent group pixdial || sudo groupadd --system pixdial
sudo usermod -aG pixdial "$USER"
sudo tee /etc/udev/rules.d/60-pixdial.rules >/dev/null <<'RULE'
SUBSYSTEM=="usb", ATTRS{idVendor}=="1cbe", ATTRS{idProduct}=="0005", GROUP="pixdial", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1cbe", ATTRS{idProduct}=="0006", GROUP="pixdial", MODE="0660"
RULE
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

Log out and back in before starting pixdial so your session picks up the new group. The rule gives group members
access to every panel with these USB IDs. It does not grant access to RAPL counters or other sensor files.
The second line is for the UNI FAN TL Wireless LCD (`1cbe:0006`), which pixdial supports as experimental: it uses
the SL V3 protocol, but no TL panel has been tested with pixdial yet.

## Sources

With no `sources` key, pixdial uses this list:

```toml
[[sources]]
type = "cpu"

[[sources]]
type = "rapl"

[[sources]]
type = "amdgpu"

[[sources]]
type = "nvml"

[[sources]]
type = "hwmon"
readings = { cpu_c = ["k10temp/Tctl", "coretemp/Package id 0"] }
```

Defining any `[[sources]]` **replaces the entire default list**. Include the defaults you want to keep.
A top-level `sources = []` disables sampling.

| Source | Reads | Options |
| --- | --- | --- |
| `cpu` | Overall and per-thread load from Linux `/proc/stat`, every 0.5 seconds | `stat`: alternate file |
| `rapl` | CPU package power from an energy counter, every second | `path`: default `/sys/class/powercap/intel-rapl:0/energy_uj`; your user must be able to read it |
| `amdgpu` | Experimental. AMD GPU power, temperature, utilisation and VRAM from the amdgpu driver's files, every second | `root`: default `/sys/class/drm` |
| `nvml` | NVIDIA GPU power, temperature and utilisation, every second | `index`: default 0; needs `libnvidia-ml.so.1` from the NVIDIA driver |
| `hwmon` | Linux hardware sensors, every second | `readings`: map of reading keys to `chip/sensor`; `root`: default `/sys/class/hwmon` |
| `command` | Numbers or JSON printed by a program | `run`: argument list; `key`: optional scalar reading name; `period`: seconds, default 5 |

hwmon accepts a sensor label or file stem, such as `k10temp/Tctl` or `corsairpsu/power1`.
A list of sensors reports the highest available value and the lowest reported critical limit (or maximum when
there is no critical limit). Configure the names your Linux drivers expose; there is no automatic PSU mapping.

The `amdgpu` source is experimental: it is tested on copies of the driver's files, not yet on a Radeon card.
It gives `gpu_c` (the edge temperature, limit: the card's critical temperature), `gpu_w` (`power1_average`, or
`power1_input` on kernels that give only that, limit: the power cap), `gpu_use` and `gpu_vram` (VRAM in use in
GiB, limit: the total). With several AMD GPUs it reads the one with the most VRAM. On a processor's built-in GPU,
`gpu_w` is the power of the whole chip. Without an AMD GPU it gives nothing and logs nothing. It looks for the
GPU on every read, so a card whose driver loads after pixdial starts is found. It comes before `nvml` in the
default list, so on a PC with an NVIDIA card and a processor's built-in AMD GPU, the NVIDIA readings win.

CPU load and RAPL need two samples. `doctor` takes those samples one second apart. An unavailable source reports
an error and is tried again; it does not stop the other sources.

### A command source

This complete config writes a live `preview.png` using fixed example readings. Save it as `preview.toml`:

```toml
layout = ["minimal"]

[[panels]]
name = "preview"
device = "png"
path = "preview.png"

[[sources]]
type = "command"
run = ["printf", "%s", '{"cpu_c":{"value":55,"unit":"°C","max":95}}']
period = 5
```

The program runs directly, without a shell, with a timeout equal to `period`. It can print a JSON object of
numbers, non-empty arrays of numbers, or objects with `value` and optional `unit`, `max`, `warn` and `label`.
With `key` set, it must print one number instead. Commands inherit your user's permissions and can use the network.

### Try a live layout without hardware

Using `preview.toml` above:

```sh
XDG_STATE_HOME="$PWD/.preview-state" pixdial --config preview.toml doctor
XDG_STATE_HOME="$PWD/.preview-state" pixdial --config preview.toml run
```

The PNG device replaces `preview.png` on each new frame. Open it while `run` is active; Ctrl-C writes a black image
and stops. The separate state directory keeps another layout selection from overriding this preview.
This works on Linux and macOS.

## Readings and ranges

Sources return `Reading` objects keyed by name. Config metadata overrides source metadata; a design uses its
fallback only when neither provides a limit. A reading becomes stale after 5 seconds or three source periods,
whichever is longer. Stale numeric measurements show a dash. Missing counts and flags use zero and false.

These are the keys the built-in designs use. Rows marked as configured data need a source you supply or map:

| Keys | Meaning | Range when no source or config limit is present |
| --- | --- | --- |
| `cpu_load`, `threads` | CPU busy percentage, overall and per thread | 0 to 100% |
| `cpu_c`, `cpu_w` | CPU temperature and package power | Temperature: 100 °C limit |
| `gpu_w`, `gpu_c`, `gpu_use` | GPU board power, temperature, utilisation | 450 W; 90 °C; 0 to 100% |
| `psu_w`, `psu_c`, `psu_fan` | PSU DC output, temperature and fan speed; configured data | 1,000 W; 70 °C |
| `pins`, `pin_total`, `pin_balance` | Per-pin current, total current, minimum/maximum balance ratio; configured data | 9.5 A per pin, warning at 95% of that |
| `quota`, `working`, `waiting` | Agent quota left (%), working sessions, waiting flag; configured data | Quota: 0 to 100% |

Example overrides, using the PSU rating and connector limits appropriate to your hardware:

```toml
[readings.psu_w]
max = 1000

[readings.pins]
max = 9.5
warn = 9.0
label = "12V-2x6"
```

Power and load scales change level at 15%, 50% and 85% of their maximum. Temperature levels start at 40% and 75%
of the distance from 20 °C to the limit, then at the limit itself; the ring extends 10 °C beyond it.
Per-pin current has its own warning threshold. These are display scales, not hardware protection controls.

## Run at login

After installing with `uv tool install`, run these Linux/systemd commands from a source checkout:

```sh
mkdir -p ~/.config/systemd/user
cp src/pixdial/data/pixdial.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pixdial
```

The unit starts `~/.local/bin/pixdial run` and restarts it after exit. Edit its `ExecStart` if your executable
is elsewhere. To inspect it or stop it and disable startup:

```sh
systemctl --user status pixdial
journalctl --user -u pixdial
systemctl --user disable --now pixdial
```

For operation after logout, an administrator may need to enable user lingering. A session-based `uaccess` rule
also needs replacing with a group rule for that use. See [Security](../SECURITY.md) before sharing logs.
