# Security

## Report privately

Use [GitHub private vulnerability reporting](https://github.com/YordiLorenzo/pixdial/security/advisories/new).
Include the affected revision, reproduction steps, expected impact and a minimal config with secrets and
device serials removed. Keep exploit details out of public issues and pull requests.

If private reporting is not available, open an issue containing only a request for a private contact channel.
Do not include the vulnerability itself. This policy covers the current development branch; 0.1.0 is unreleased.

## Permissions and hardware

pixdial runs as the invoking user. The SL V3 driver needs read and write access to the matching USB device node
and claims its interface through Linux usbdevfs. The supplied udev rule grants that access to the user with an
active local login; a group rule can grant it to named group members instead.

The built-in driver sends revision and version queries, frame-rate setup, frames and brightness. It sends no
firmware-write, reboot, panel-rotation, startup-image or storage commands. Frame rotation happens on the host.
It does not control fan speed, RGB lighting or cooling policy. Normal shutdown sets brightness to zero;
a forced kill or disconnected device may prevent that final command.

The fixed DES key in the SL V3 protocol is shared device compatibility data, not a credential.
The protocol should not be treated as authenticated or secure transport.

## Sources, plugins and network

Built-in CPU, RAPL and hwmon sources read local files. NVML queries the local NVIDIA library.
There is no telemetry, built-in network service or automatic download at runtime.

Python plugins execute code with the user's permissions. The command source executes the configured argument
list directly, without a shell, and can run any program your user can run. Either can read or write files and
use the network. Configs containing such sources are code, not passive data. `pixdial doctor` reads sources and
therefore also executes configured commands.

`render` writes images to its chosen directory. PNG and plugin file devices write to their configured paths;
an existing output file can be replaced. `show` saves the layout in the user's XDG state directory.
pixdial does not install udev rules or a systemd service automatically.

## Logs and diagnostics

CLI output can contain USB serials, device nodes, file paths, readings and source errors. The optional systemd
unit sends logs to the user journal. Review diagnostic output before sharing it, especially output from your
own command sources or plugins.
