# Plugins

A plugin adds designs, sources or devices through Python entry points. Install it into the same environment as
pixdial. Built-in names cannot be replaced by plugins; `pixdial list` and `pixdial doctor` report plugins that
fail to load.

## Run the example

From a source checkout on Linux or macOS:

```sh
uv sync --locked
uv pip install --no-deps -e examples/plugin
uv run pixdial list
uv run pixdial render big --out build/plugin-preview
```

The example's `big` design reads `loadavg`. The renderer's built-in demo readings do not include that key, so
this preview correctly shows a dash. To feed it the live source, save this as `plugin.toml`:

```toml
layout = ["big"]

[[panels]]
name = "preview"
device = "png"
path = "build/plugin-preview/live.png"

[[sources]]
type = "loadavg"
```

```sh
XDG_STATE_HOME="$PWD/build/plugin-state" uv run pixdial --config plugin.toml doctor
XDG_STATE_HOME="$PWD/build/plugin-state" uv run pixdial --config plugin.toml run
```

Open `build/plugin-preview/live.png` while it runs. Ctrl-C stops it and writes a black frame.
An exact `uv sync` can remove the extra plugin; repeat the editable install if needed.

## Register classes

[examples/plugin/pyproject.toml](../examples/plugin/pyproject.toml) registers all three kinds:

```toml
[project.entry-points."pixdial.designs"]
big = "pixdial_example:Big"

[project.entry-points."pixdial.sources"]
loadavg = "pixdial_example:LoadAverage"

[project.entry-points."pixdial.devices"]
folder = "pixdial_example:Folder"
```

These tables belong in a package's `pyproject.toml`, alongside its project metadata and build configuration.
The target must subclass `Design`, `Source` or `Device` for its group.

A source or device can also be named as `type = "module:Class"` or `device = "module:Class"` in the config,
provided that module is on the Python path. Designs must use entry points to appear in the CLI catalog.
`uv tool` installs are isolated from your project environment; develop plugins in the checkout's virtualenv.

## Designs

Start with the runnable design in the [README](../README.md#build-a-design) or the fully typed
[`Big` example](../examples/plugin/pixdial_example.py).

| Hook or field | Contract |
| --- | --- |
| `name`, `shows` | A short identifier and a one-line description. `about` adds detail to the rendered gallery. |
| `update(snapshot, now, dt)` | Read the snapshot, update state and return `(still_key, moving_key)`. Keys must be hashable. `now` and `dt` are monotonic seconds and elapsed seconds. |
| `still()` | Return the drawing from `Frame.finish()`. Called when the still key changes, at most 10 times a second in the runtime. |
| `moving(pixels, now)` | Optional: paint into a copy of the still picture. Set `fps` and return `self.animating(now)` as the moving key while active, otherwise `None`. |
| `trails` | A tuple of `TrailSpec` requests, available from `snapshot.trail(spec)` even after another design has been on screen. |
| `reads`, `needs` | The reading keys it shows, and those it is mostly dashes without. While no source gives one of `needs`, the default layout and rotation leave it out. `doctor --share` lists the `reads` no source gives. |

Coordinates use the panel's 400 × 400 grid; the drawing kit applies the requested render scale.
Designs should only render from snapshots, with no I/O. Use `Eased` for numbers that glide to their next value;
round the still key with `rnd` to avoid redraws for invisible changes.

`self.frame()`, `self.gauge()`, `self.label()` and `self.line()` handle the shared layout.
`Frame.number()` centres the digits and places the unit beside them; `None` draws a dash.
`LOAD`, `share(maximum)`, `temperature(limit)` and `current(rating, warning)` map readings to gauge positions
and theme colours. `snapshot.max(key)` reads a config override first, then a hardware-reported limit.

Use `paint`, `disc` and `glow_disc` for motion; keep it cheap enough for each frame. Set `under_text = True` when
motion passes behind labels, so the runtime composites text after it. `design.render(now)` combines both drawing
passes for standalone use; the runtime caches the still pass between frames.

For history, declare a request such as `TrailSpec("psu_w", period=1.0, span=120.0)` in `trails`.
`Trail.t` and `Trail.v` contain timestamps and values; missing samples use NaN. A design can select gallery states
with `previews`, chosen from `idle`, `busy`, `waiting`, `full` and `missing`.

## Sources

This is the source used by the example plugin:

```python
import os

from pixdial.readings import Reading
from pixdial.sources import Source


class LoadAverage(Source):
    period = 5.0

    def read(self) -> dict[str, Reading]:
        return {"loadavg": Reading(os.getloadavg()[0], max=os.cpu_count())}
```

Each source is sampled in its own thread. Return a mapping of reading keys to `Reading` objects; arrays should
be NumPy arrays. Omit unavailable values, or raise `OSError` or `ValueError` if the whole read fails.
The runtime retries on the next period and keeps the other sources running. Old readings expire after
`max(5, 3 * period)` seconds. When two sources report the same key, the later source in the config wins while fresh.

A reading has `value`, `unit`, `max`, `warn` and `label`. Config metadata overrides the last three.
Optional `reset()` drops handles after resume; `close()` releases resources at shutdown. Optional `gives()`
returns the reading keys the source can give on this machine, without reading it; the default `None` means any key,
which keeps every design in the default rotation.
See [Configuration](config.md#readings-and-ranges) for keys used by built-in designs and
[the command source](config.md#a-command-source) for a JSON alternative.

## Devices

A complete device that writes numbered frames, taken from the example plugin:

```python
from pathlib import Path

from PIL import Image

from pixdial.devices import Device


class Folder(Device):
    def __init__(self, path: str) -> None:
        self.path, self.count = Path(path).expanduser(), 0

    def open(self) -> str:
        self.path.mkdir(parents=True, exist_ok=True)
        return f"writing {self.path}"

    def show(self, image: Image.Image) -> None:
        self.count += 1
        image.save(self.path / f"{self.count:06d}.jpg", quality=90)

    def off(self) -> None:
        pass

    def close(self) -> None:
        pass
```

`show()` receives a 400 × 400 RGB Pillow image. Config options are passed to the constructor and checked by name.
`open()` returns a short status string; an `OSError` causes a retry after 10 seconds.
`show()` can raise `OSError` on disconnect, which closes the device so it can be reopened.
Implement `off()` to blank physical hardware on normal shutdown and `close()` to release it.
The file example has nothing to turn off.

Optional `discover()` returns `Found` records for `pixdial devices`; `problem()` reports a permission or presence
problem for `doctor` without opening the device. Set `id` to the discovery identifier so the CLI can match it to
its config entry. A `Found` record's `note` is printed beside it, and a class's `note` beside its name in
`pixdial list`; the built-in drivers use them to mark experimental models. Other resolutions need corresponding
rendering support, not only a new `Device.size`.

Keep hardware tests separate from the default suite. Record protocol sources and exactly which commands the
driver sends. Do not add firmware writes as part of frame delivery.
