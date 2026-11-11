# Security

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/YordiLorenzo/pixdial/security/advisories/new).
Include the affected revision, reproduction steps, expected impact and a minimal config with secrets and
device serials removed. Keep exploit details out of public issues and pull requests.

If private reporting is not available, open an issue containing only a request for a private contact channel.
Do not include the vulnerability itself. This policy covers the latest release and the main branch.

## Permissions and hardware

pixdial runs as the invoking user and needs no root; its systemd user service runs as that user too. The SL V3
driver needs read and write access to the matching USB device node and claims its interface through Linux
usbdevfs. The supplied udev rule grants that access to the user with an active local login; a group rule can grant
it to named group members instead.

`pixdial setup` is the one command that runs anything as root, and only when the panels need it. It prints the
exact commands first, then runs them through `sudo sh -e`, so sudo asks for your password. They write
`/etc/udev/rules.d/60-pixdial.rules` and reload udev. On a machine where the service starts with nobody logged in
at it (linger, or no session at its seat), they also create the `pixdial` system group and add your user to it,
and the rule gives the panels to that group instead of the user at the seat. `pixdial setup --dry-run` prints the
commands and runs nothing.

The built-in driver sends revision and version queries, frame-rate setup, frames and brightness. It sends no
firmware-write, reboot, panel-rotation, startup-image or storage commands. Frame rotation happens on the host.
It does not control fan speed, RGB lighting or cooling policy. Normal shutdown sets brightness to zero;
a forced kill or disconnected device may prevent that final command.

The fixed DES key in the SL V3 protocol is shared device compatibility data, not a credential.
The protocol should not be treated as authenticated or secure transport.

## Sources, plugins and network

Built-in CPU, RAPL, hwmon and amdgpu sources read local files. NVML queries the local NVIDIA library.
There is no telemetry, built-in network service or automatic download at runtime.

Python plugins execute code with the user's permissions. The command source executes the configured argument
list directly, without a shell, and can run any program your user can run. Either can read or write files and
use the network. Configs containing such sources are code, not passive data. `pixdial doctor` reads sources and
therefore also executes configured commands.

`render` writes images to its chosen directory. PNG and plugin file devices write to their configured paths;
an existing output file can be replaced. `show` saves the layout in the user's XDG state directory. `setup`
writes the config file, and asks before it replaces one. `service install` writes a systemd user unit to
`~/.config/systemd/user/` and enables it, as your user; `service remove` stops it and deletes it.

## Logs and diagnostics

CLI output can contain USB serials, device nodes, file paths, readings and source errors. The optional systemd
unit sends logs to the user journal. Review diagnostic output before sharing it, especially output from your
own command sources or plugins.

`pixdial doctor --share` prints a report for issues with each serial replaced by panel-1, panel-2, the home
folder replaced by `~` and the hostname replaced by `host`. Readings and source errors stay in it. To read each
panel's firmware version, it opens each panel that no program holds for a moment and leaves it dark.
