# Contributing

Designs, data sources, support for more screens and reproducible bug reports are welcome.
Read [the architecture](docs/architecture.md) and [plugin guide](docs/plugins.md) before adding an extension.

## Development setup

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). Linux is required for the physical USB driver
and built-in system sensors; rendering and the test suite also run on macOS without hardware.

```sh
git clone https://github.com/YordiLorenzo/pixdial.git
cd pixdial
uv sync --locked
```

Run the same checks as CI:

```sh
uv run ruff check
uv run mypy
uv run pytest -q
```

CI runs on Ubuntu with Python 3.12 and 3.13. `mypy` uses the strict settings and file list in `pyproject.toml`.
Tests use fake hardware and synthetic readings; no attached panel is needed.

`uv run pytest -m hardware` runs the one test on real panels, which the normal run leaves out. It needs Linux, at
least one SL V3 or TL panel with the udev rule, and no other program with a panel open: stop pixdial first
(`systemctl --user stop pixdial`). It sends 30 frames a second to every panel at once for 10 minutes
(`--hardware-seconds` changes that), then resets each panel once over USB. It prints a report: frames sent and
acknowledged, frames per second, CPU, resident memory and the time each panel took to come back after its reset.
Format files you change with `uv run ruff format PATH`, then rerun the checks.

## Golden images

`tests/test_golden.py` compares every built-in design in three themes and four states against committed images.
A mismatch writes a neighbouring `.actual.png` for inspection. Small FreeType edge differences are tolerated;
changes in layout or colour should fail.

For an intentional visual change, inspect the difference first, then regenerate only the affected design.
For example, after changing `crown`:

```sh
UPDATE_GOLDEN=1 uv run pytest -q tests/test_golden.py -k crown
uv run pytest -q tests/test_golden.py
```

Review the resulting image diff before committing. Do not regenerate goldens to silence an unexplained failure.
Use `uv run pixdial render --gallery build/gallery` to inspect the full built-in gallery in
`build/gallery/gallery.html`.

## Add an extension

| Kind | Start here | What to verify |
| --- | --- | --- |
| Design | Subclass `Design`; see [Build a design](README.md#build-a-design) | Every theme, missing readings, full scale and text inside the round edge. Add it to `BUILTIN` for a built-in design, or register an entry point for a plugin. |
| Source | Subclass `Source`; see [Sources](docs/plugins.md#sources) | Units, reported limits, unavailable sensors, stale readings and reset after resume. Use fixtures or fake readers in tests. |
| Device | Subclass `Device`; see [Devices](docs/plugins.md#devices) | Exact command bytes, frame size, permissions, disconnect/reconnect and normal shutdown. Record protocol references and real hardware tested. |

[examples/plugin](examples/plugin/) has an installable package covering all three kinds. Source and device
constructor arguments become config options. Keep defaults safe and errors specific to the option or device.
Do not require real hardware or network services in the normal test suite.

For a new built-in design, `test_golden.py` picks it up from `BUILTIN`; generate and review its golden images
with the same filtered command as above. For new hardware, separate tested support from protocol similarities.

## Rebuild README graphics

```sh
uv run python docs/images/build.py
```

The script invokes `pixdial render` for the 14 designs, the three theme samples and the animated gallery output.
It composes `docs/images/designs.png`, `themes.png` and `demo.webp` on the brand's coffee-night background.
Intermediate renders stay in ignored `build/readme/`; each final image must be under 1.5 MB.
Open all three outputs and check labels and circular crops. The existing banner and logos are separate brand assets.

## Website

`site/` is the static GitHub Pages site: HTML, CSS and vanilla JavaScript, with no analytics or external font
requests. Edit the page directly; there is no framework build. Keep claims aligned with the README and code.

Rebuild the images and check local links:

```sh
uv run python site/build.py
uv run python site/check.py
uv run ruff check
uv run mypy
```

The image script uses `pixdial render --state busy --scale 4` with an isolated config and no sources. It creates
real 1600 × 1600 renders for all 14 designs and three crown themes in ignored `build/site/renders/`. It encodes
400/640/960/1280-pixel WebP variants, plus the 1600-pixel crown hero, without upscaling. The logo, SVG favicon and
social preview come from `docs/images/`. The fitted ICO/32px/Apple icons and Space Grotesk Latin variable WOFF2
are committed brand assets; the font's OFL is in `site/fonts/OFL.txt`. Rebuilding images needs no brand-kit path.
Keep all published files below 4 MB and the initial browser load below 1 MB. Below-fold images should lazy-load.

To preview with the same `/pixdial/` prefix as Pages, create a local server root (once) and serve it:

```sh
mkdir -p build/pages
ln -s ../../site build/pages/pixdial
python3 -m http.server 8765 --bind 127.0.0.1 --directory build/pages
```

Open `http://127.0.0.1:8765/pixdial/`. Check 390, 768, 1024 and 1440-pixel widths, keyboard focus, copy buttons,
all 14 preview designs, pause/resume and reduced motion. Reduced motion stops automatic rotation and fades;
previous/next still work. With JavaScript disabled, the first preview, full gallery, commands and FAQ remain usable.

`.github/workflows/pages.yml` deploys committed `site/` files on matching pushes to `main` or manual dispatch.
The deploy job skips private repositories. When the repository is public, enable **Settings → Pages → GitHub
Actions** and run **Actions → Pages → Run workflow**. The production URL is
`https://yordilorenzo.github.io/pixdial/`; publishing is separate from building or previewing locally.
GitHub Pages project sites share the origin's `/robots.txt`; `site/robots.txt` records the intended policy and
sitemap, but does not override that origin-wide file.

## Releasing

1. Bump the version in `pyproject.toml` and `src/pixdial/__init__.py`, refresh `uv.lock`
   with `uv lock`, and update `CHANGELOG.md`. Run the CI checks above.
2. Commit the release changes and create the matching `vX.Y.Z` git tag.
3. Build and validate the release artifacts:

   ```sh
   uv build
   uvx twine check dist/pixdial-X.Y.Z*
   ```

   Replace `X.Y.Z` with the release version and check the sdist and wheel before uploading.
4. Publish those artifacts with `uv publish dist/pixdial-X.Y.Z*`, push the release commit
   and tag, and create the GitHub release with `gh release create vX.Y.Z dist/pixdial-X.Y.Z*`.
   Use the changelog entry as the release notes. Publishing requires PyPI credentials and
   GitHub push/release access.
5. Update the version and sdist hash in [packaging/](packaging/README.md), including the
   AUR source URL and `.SRCINFO`. Build and submit the AUR and nixpkgs updates using that
   directory's instructions.

## Send a change

1. Keep the change focused and explain what now works, with a reproduction for a fix.
2. Run the lint, type and test commands above; include results and any checks you could not run.
3. Include render images for a visual change and update docs when config or behaviour changes.
4. Describe hardware testing separately from mocked tests. Remove serials, private paths and credentials from logs.
5. Open a pull request. Contributions must be compatible with GPL-3.0-or-later; retain third-party notices.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
