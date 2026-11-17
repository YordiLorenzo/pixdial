# Troubleshooting

Run `pixdial doctor` first. It checks config, fonts, plugins, panel access, layout and source readings.
`FAIL` means a configured part cannot work; `skip` means pixdial can run without it. Each failure links here.

## Device busy

Message: `claimed by <program> (pid <n>), so pixdial can't open it`, or `Device or resource busy` (`EBUSY`).

Cause: another program has the LCD open. Each LCD accepts one program at a time. If the pixdial service is
running, stop it before trying `pixdial run` in a terminal:

```sh
systemctl --user stop pixdial
pixdial run
```

After Ctrl-C, use `systemctl --user start pixdial` to return to the service.

For lian-li-linux, remove only the LCDs pixdial will drive from the `lcds` entries in its `config.json`.
For its user service, edit `~/.config/lianli/config.json`, then run:

```sh
systemctl --user restart lianli-daemon
pixdial doctor
```

For its system service, edit `/var/lib/lianli/config.json` with `sudoedit`, then run:

```sh
sudo systemctl restart lianli-daemon-system
pixdial doctor
```

Use the commands for the service you run. Fan speed and RGB can stay with that program.
If you later return the LCDs to it, restore their `lcds` entries and restart the same daemon.

## Permission denied

Message: `no read and write access to ...: pixdial setup gives it`, or `Permission denied` for `/dev/bus/usb/...`.

Cause: your user cannot open the panel's USB device node. Install the permission rule:

```sh
pixdial setup --dry-run
pixdial setup
pixdial devices
```

If setup adds you to the `pixdial` group, log out and back in first; with linger, reboot. Do not run pixdial as
root. [USB permissions](config.md#usb-permissions) explains local-seat and group access. Permission errors on
an `energy_uj` file belong to [CPU power](#cpu-power).

## Black panel

Message: `none in the config, and none attached`, `no SL V3 or TL LCD with serial ... attached`, or a dark LCD
with no error yet.

Cause: the USB cable is missing, the configured serial is wrong, or pixdial is stopped. Normal shutdown turns
the LCD dark. Each LCD needs its own USB cable to a USB 2 header on the motherboard; the wireless dongle cannot
send frames. Check the connection and detected serials:

```sh
lsusb | grep 1cbe
pixdial devices
pixdial doctor
```

If the panel is listed but its serial differs from your config, run `pixdial setup` to write the detected
serials. Setup asks before replacing an existing config. Once doctor passes, start the service:

```sh
pixdial service install
pixdial service status
```

If the service still fails, read its error with `journalctl --user -u pixdial -n 50 --no-pager` and follow the
matching entry on this page. A panel claimed by another program belongs to [Device busy](#device-busy).

## Missing raqm

Message: `skip  raqm  no`. Older pixdial versions can instead report that font features require libraqm.

Cause: Pillow cannot use raqm for text layout, often because FriBiDi is absent. Since 0.1.1, pixdial renders
without raqm on Linux and macOS. Text is slightly wider because it uses basic font layout. Upgrade if rendering
still fails:

```sh
uv tool upgrade pixdial
pixdial render crown --out preview
```

To enable raqm with a Pillow build that loads FriBiDi separately, install FriBiDi for your system:

| System | Command |
| --- | --- |
| Debian or Ubuntu | `sudo apt install libfribidi0` |
| Fedora Workstation | `sudo dnf install fribidi` |
| Arch Linux | `sudo pacman -S fribidi` |
| macOS with Homebrew | `brew install fribidi` |

Then run `pixdial doctor` again. A Pillow built without raqm needs a different build; see
[Pillow's installation guide](https://pillow.readthedocs.io/en/stable/installation/basic-installation.html).
On [atomic desktops](atomic-desktops.md), use the working basic layout rather than changing the OS image for
an optional font feature.

## CPU power

Message: `Permission denied` for an `energy_uj` file under `source rapl`.

Cause: Linux restricts RAPL energy counters to root. CPU power (`cpu_w`) stays missing in crown and flow.
Read the [CVE-2020-8694 trade-off](config.md#cpu-power-permissions) before granting the panel group access:

```sh
pixdial setup --rapl --dry-run
pixdial setup --rapl
```

Log out and back in for the new group membership; with linger, reboot. Then run `pixdial doctor` again.
If the message is `No such file or directory`, a permission rule cannot create the counter. Check the
hardware and driver support, and the `path` option for the [RAPL source](config.md#sources).

## Source readings

Message: `FAIL  source <name> ...`, or `skip  source <name> ...` for an unavailable default source.

Cause: a driver, sensor file or configured command is unavailable. A missing default source is optional;
an explicitly configured source is a failure. Use the error's path or command and the [source options](config.md#sources)
to correct the config, then rerun:

```sh
pixdial doctor
```

NVIDIA readings need a working NVIDIA driver; `nvidia-smi` checks it. Install or repair that driver through
your distribution. AMD readings come from the experimental `amdgpu` source. If it gives nothing on a Radeon,
use the [Radeon report](https://github.com/YordiLorenzo/pixdial/issues/new?template=radeon.yml).
The default rotation leaves out designs with no source for their required readings.

## Configuration

Message: `FAIL  config`, `FAIL  layout`, `FAIL  sources` or `FAIL  panels`, followed by a key, path or value.

Cause: invalid TOML, an unknown name, a missing file or an option with the wrong type. Fix the named value using
the [configuration guide](config.md). Use the same path when checking a custom config:

```sh
pixdial --config "/path/to/panel config.toml" doctor
```

`pixdial setup` can create a panel config if you have none. It asks before replacing one. A config error exits
with status 2 in `run`; the service stops until the config is fixed. Then use `systemctl --user restart pixdial`.

## Missing fonts

Message: `missing Lato Black, Bold, Regular`, or a subset of those weights.

Cause: the installed package is incomplete. These fonts ship with pixdial; no system font package is needed.
For a uv install, reinstall and check:

```sh
uv tool upgrade --reinstall-package pixdial pixdial
pixdial doctor
```

For a distribution package, reinstall it through the same package manager.

## Plugins

Message: `FAIL  plugin <name> ...`, followed by an import error, wrong base class or duplicate name.

Cause: the plugin cannot load in pixdial's environment. Install its dependencies in that environment, correct
its entry point or choose a name that does not replace a built-in. The [plugin guide](plugins.md) covers each kind.
Check the result with:

```sh
pixdial list
pixdial doctor
```

A `declares plugin API ...; pixdial supports ...` warning means the plugin targets another API major.
Use a compatible plugin or pixdial version; the plugin still loads, but may fail when used.

## Report a problem

Open a [bug report](https://github.com/YordiLorenzo/pixdial/issues/new?template=bug.yml) with `pixdial doctor --share`.
It removes panel serials, your hostname and your home path. It briefly opens free panels to read their firmware,
then leaves them dark; it does not open a panel already held by another program. Review the output before sharing it.

For a log, stop the service first, run until the problem appears, then press Ctrl-C and start the service again:

```sh
systemctl --user stop pixdial
pixdial run --debug --log-file pixdial.log
systemctl --user start pixdial
```

Logs contain file paths. Read them before sharing. For upgrades, rollback or removal, see
[maintenance](maintenance.md).
