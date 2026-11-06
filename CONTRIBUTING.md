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

## Send a change

1. Keep the change focused and explain what now works, with a reproduction for a fix.
2. Run the lint, type and test commands above; include results and any checks you could not run.
3. Include render images for a visual change and update docs when config or behaviour changes.
4. Describe hardware testing separately from mocked tests. Remove serials, private paths and credentials from logs.
5. Open a pull request. Contributions must be compatible with GPL-3.0-or-later; retain third-party notices.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
