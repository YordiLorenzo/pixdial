# Bazzite, Fedora Atomic and SteamOS

These instructions install pixdial and Python in your home folder with uv. The USB permission rule goes in
`/etc/udev/rules.d/`. No rpm-ostree layering or Distrobox is needed.

| Distribution | Test status |
| --- | --- |
| Bazzite | Untested with pixdial, including Gaming Mode and updates. |
| Fedora Atomic desktops, including Silverblue and Kinoite | Untested with pixdial, including updates. |
| SteamOS | Untested with pixdial, including Gaming Mode, USB access and persistence after updates. |

Use a terminal on the host. On SteamOS, switch to Desktop Mode first. You need an internet connection for the
install, sudo access for the udev rule, and a [supported LCD](../README.md#supported-hardware) connected by USB.

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if it is not already available:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

Install pixdial with a Python version tested by its CI. uv downloads Python if needed:

```sh
uv tool install --python 3.12 pixdial
uv tool update-shell
pixdial --version
```

## USB access and config

Preview setup, then apply it:

```sh
pixdial setup --dry-run
pixdial setup
```

Setup installs `/etc/udev/rules.d/60-pixdial.rules` through sudo and reloads udev. With an active local login,
the file contains these rules:

```udev
SUBSYSTEM=="usb", ATTRS{idVendor}=="1cbe", ATTRS{idProduct}=="0005", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1cbe", ATTRS{idProduct}=="0006", TAG+="uaccess"
```

With linger or no active local seat, setup uses the [group rule](config.md#usb-permissions) instead.
Log out and back in for a new group membership; with linger, reboot. Setup also writes your panel config in
`~/.config/pixdial/config.toml`. Keep the udev rule on the host: a container's `/etc` does not configure host USB
access. Fedora Atomic keeps writable configuration in `/etc`; see
[Fedora's filesystem description](https://fedoramagazine.org/pieces-of-fedora-silverblue/).

On SteamOS, if writing the rule reports `Read-only file system`, stop there. This guide does not require
unlocking the system image. Valve warns that changes outside Flatpak may be lost during updates in its
[Desktop FAQ](https://help.steampowered.com/en/faqs/view/671A-4453-E8D2-323C/).
After an OS update, check `pixdial devices` and `pixdial doctor`; repeat setup if the rule is missing.

CPU power access is separate and off by default. Read the [RAPL trade-off](config.md#cpu-power-permissions)
before choosing `pixdial setup --rapl`.

## Start at login

```sh
pixdial doctor
pixdial service install
pixdial service status
```

The service runs as your user. Access while switching between Desktop Mode and Gaming Mode has not been tested.
If the panels stop working after a switch, run `pixdial doctor` in the new session before changing permissions.
Each LCD needs its own USB connection; the wireless dongle does not carry frames.
