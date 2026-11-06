# Packaging

Recipes for package repositories that keep their definitions outside this repo. Both pin
the released PyPI sdist for pixdial 0.1.0. Update the version and checksum for each release,
and the content-addressed PyPI URL in `PKGBUILD`, then regenerate `.SRCINFO`.
Homebrew is intentionally omitted: pixdial drives physical panels only on Linux.

| Target | Files here | Submission destination |
| ------ | ---------- | ---------------------- |
| AUR | `aur/PKGBUILD`, `aur/.SRCINFO` | `ssh://aur@aur.archlinux.org/pixdial.git` |
| nixpkgs | `nix/package.nix` | `pkgs/by-name/pi/pixdial/package.nix` in a nixpkgs pull request |

## Panel access without root

The bundled `src/pixdial/data/60-pixdial.rules` grants the active local user's session
access to supported USB panels through udev's `uaccess` tag. Installing and activating
this rule is what makes the panel usable without running pixdial as root. The AUR package
installs it at `/usr/lib/udev/rules.d/60-pixdial.rules`; the Nix package installs it at
`$out/lib/udev/rules.d/60-pixdial.rules`.

After installing on Arch, reload the rules and apply them to attached panels:

```sh
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

On NixOS, installing the executable alone does not activate its rules. Add this to the
system configuration and rebuild with `sudo nixos-rebuild switch`:

```nix
environment.systemPackages = [ pkgs.pixdial ];
services.udev.packages = [ pkgs.pixdial ];
```

Reconnect the panel if access has not updated. On other Linux distributions using Nix,
the host administrator must install the packaged rule into the host's udev rules directory
and reload it. Headless machines without an active local login need the group-based
alternative described in the rule's comments.

Both recipes retain the project's GPL-3.0-or-later licence and the bundled Lato fonts'
OFL-1.1 notice.

## AUR

1. Create an [AUR account](https://aur.archlinux.org/register) and register an SSH public
   key in its settings. Use an Arch Linux environment with `base-devel` installed for
   validation; no PyPI credentials are needed. Check whether `pixdial` already has an
   AUR maintainer before attempting a first submission.
2. From this pixdial checkout, copy the recipes into the AUR checkout:

   ```sh
   git clone ssh://aur@aur.archlinux.org/pixdial.git ../pixdial-aur
   cp packaging/aur/PKGBUILD packaging/aur/.SRCINFO ../pixdial-aur/
   ```

3. Build with tests enabled and regenerate the metadata on Arch:

   ```sh
   cd ../pixdial-aur
   makepkg --syncdeps --cleanbuild
   makepkg --printsrcinfo > .SRCINFO
   git diff -- PKGBUILD .SRCINFO
   ```

   Prefer an additional clean-chroot build with Arch's `devtools` before submission.
   Do not skip `check()`: it runs the full pytest suite, including the sdist's golden images,
   without real hardware.
4. Review the files, then submit from that AUR checkout:

   ```sh
   git add PKGBUILD .SRCINFO
   git commit -m "pixdial 0.1.0"
   git push
   ```

### Hand-written .SRCINFO fields

The initial `.SRCINFO` was written by hand because `makepkg` is unavailable on the authoring
machine. It contains only the following fields, derived from `PKGBUILD`; regenerate it
with `makepkg --printsrcinfo` on Arch before submitting.

| Field | Derivation / value |
| ----- | ------------------ |
| `pkgbase`, `pkgname` | Both use `pkgname`: `pixdial` (one package). |
| `pkgdesc` | Literal `pkgdesc`: `A Python SDK and CLI for hardware screens on Linux`. |
| `pkgver`, `pkgrel` | `0.1.0`, `1`. |
| `url` | `https://github.com/YordiLorenzo/pixdial`. |
| `arch` | One row from `arch`: `any` (pure Python; Arch is Linux). |
| `license` | Two rows from `license`: `GPL-3.0-or-later`, `OFL-1.1`. |
| `checkdepends` | One row: `python-pytest`. |
| `makedepends` | Four rows: `python-build`, `python-installer`, `python-hatchling`, `python-hatch-fancy-pypi-readme`. |
| `depends` | Four rows: `python>=3.12`, `python-numpy`, `python-pillow`, `python-cryptography`. |
| `source` | The literal PyPI URL with `$pkgname` and `$pkgver` expanded to `pixdial` and `0.1.0`. |
| `sha256sums` | `924e5ea534af537ecfca0210d455b8df2a6c16f6bfd204c19d1a696414fb07f2`. |

The maintainer comment and `build()`, `check()` and `package()` functions are not `.SRCINFO`
fields. No split-package overrides or extra metadata fields are used.

## nixpkgs

1. Use a GitHub account to fork [NixOS/nixpkgs](https://github.com/NixOS/nixpkgs), then
   clone the fork next to this pixdial checkout as `../nixpkgs`. Authenticate pushes with
   a GitHub SSH key or HTTPS credentials. Build on Linux with Nix, or use a Linux remote builder.
2. Copy the derivation from this pixdial checkout:

   ```sh
   mkdir -p ../nixpkgs/pkgs/by-name/pi/pixdial
   cp packaging/nix/package.nix ../nixpkgs/pkgs/by-name/pi/pixdial/package.nix
   ```

   The recipe references `yordilorenzo`. If that entry is absent, add exactly this to
   `maintainers/maintainer-list.nix` (do not duplicate an existing entry):

   ```nix
     yordilorenzo = {
       email = "yordilorenzo@gmail.com";
       github = "YordiLorenzo";
       githubId = 7012112;
       name = "Yordi de Kleijn";
     };
   ```

3. In the nixpkgs checkout, build and check the installed executable and udev rule:

   ```sh
   cd ../nixpkgs
   nix-instantiate --parse pkgs/by-name/pi/pixdial/package.nix >/dev/null
   nix-build -A pixdial
   ./result/bin/pixdial --version
   test -f result/lib/udev/rules.d/60-pixdial.rules
   ```

   The build runs pytest through `pytestCheckHook` and checks that `pixdial` imports.
4. Commit any new maintainer entry separately as `maintainers: add yordilorenzo`, then
   the derivation as `pixdial: init at 0.1.0`. Push your branch and open a nixpkgs pull
   request with the build results. A PyPI upload token is not needed for this submission.

## Release updates

Follow [Releasing](../CONTRIBUTING.md#releasing) first. Copy the new sdist URL and SHA256
from PyPI, update `pkgver`, reset `pkgrel` to `1`, and replace `source` and `sha256sums` in
`aur/PKGBUILD`. Regenerate `.SRCINFO` on Arch. Update `version` and the SRI `hash` in
`nix/package.nix`; `nix hash convert --hash-algo sha256 --to sri HEX_SHA256` converts the
same sdist checksum. Rebuild both packages before submitting their updates.
