# Upgrade and uninstall

## Upgrade

For a uv install:

```sh
uv tool upgrade pixdial
pixdial --version
pixdial doctor
```

If you use the service, run `systemctl --user restart pixdial` to load the new version. With a manual `pixdial run`,
stop it with Ctrl-C and start it again. Upgrades keep your config and state. A pipx install uses
`pipx upgrade pixdial`; distribution packages use their package manager.

To roll back, use `uv tool install pixdial==<the previous version>`, replacing the placeholder with the release
you used before. For example:

```sh
uv tool install pixdial==0.1.2
pixdial doctor
```

Restart the service or manual process again. Restore your saved config if the older release cannot read newer
options. The [changelog](../CHANGELOG.md) and [versioning policy](../CONTRIBUTING.md#versioning-policy) describe
compatibility changes.

## Uninstall

Remove the service before uninstalling the command:

```sh
pixdial service remove
```

Remove the USB rule and the optional RAPL rule, then reload udev:

```sh
sudo rm -f /etc/udev/rules.d/60-pixdial.rules /etc/udev/rules.d/60-pixdial-rapl.rules
sudo udevadm control --reload-rules
```

Removing a rule does not reset permissions on existing devices. Unplug and reconnect the panel USB cables to
drop the old USB access. If you enabled RAPL access, restore root-only reads on its existing counters:

```sh
sudo find -L /sys/class/powercap -maxdepth 2 -path '/sys/class/powercap/intel-rapl:*/energy_uj' \
  -exec chmod 0400 {} + -exec chgrp root {} +
```

A reboot after removing the rules also resets those permissions. If setup added your user to the `pixdial`
group, remove that membership, then log out and back in:

```sh
sudo gpasswd -d "$USER" pixdial
```

Keep a copy of any config you want to reuse. The next command asks before deleting files in pixdial's config
and state folders. It uses your XDG paths, defaulting to `~/.config/pixdial` and `~/.local/state/pixdial`:

```sh
rm -ri -- "${XDG_CONFIG_HOME:-$HOME/.config}/pixdial" "${XDG_STATE_HOME:-$HOME/.local/state}/pixdial"
uv tool uninstall pixdial
```

Remove a config passed with `--config` and saved render files separately if you no longer need them.
For pipx, use `pipx uninstall pixdial`; for a distribution package, use its package manager. Package-owned rules
under `/usr/lib/udev/rules.d` go away with that package. To give the LCDs back to another program, follow
[Device busy](troubleshooting.md#device-busy).
