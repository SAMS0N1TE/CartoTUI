# Architecture

For anyone working on the code.

## The frame

```
tiles -> image -> tone -> glyphs -> cell overlays -> screen
```

1. `vector_source` or `cache` fetches tiles
2. `raster_vector.rasterise_view` or `libcarto` draws vector tiles to a PIL
   image, or `composite.composite_from_tiles` stitches raster tiles
3. `composite.apply_image_adjustments` applies the tone knobs
4. `rendering.renderer` turns the image into styled terminal cells
5. `ui.map_overlay` and `ui.aircraft_overlay` stamp labels and aircraft onto
   those cells
6. prompt_toolkit draws it

Rendering happens on a worker thread. `map_control` holds a queue, dedupes on a
snapshot key built from the map state, and drops stale frames.

## Where things live

| Path | What |
| --- | --- |
| `cartotui/cli.py` | Arg parsing |
| `cartotui/config.py` | Defaults and validation. Every key is range checked here |
| `cartotui/composite.py` | Raster stitching, tone pipeline |
| `cartotui/raster_vector.py` | Python vector renderer |
| `cartotui/rendering/renderer.py` | Image to cells. One class per view mode |
| `cartotui/rendering/threshold.py` | Luminance to fill levels |
| `cartotui/radar.py` | RainViewer |
| `cartotui/traffic/` | ADS-B sources and the aircraft registry |
| `cartotui/themes/` | Built-in theme JSON |
| `cartotui/ui/` | prompt_toolkit app, map control, sidebar |
| `cartotui/ui/widgets/` | Floating panels |
| `libcarto/` | Native C renderer |
| `bindings/python/carto_ffi.py` | ctypes wrapper for it |
| `tools/preview_harness.py` | Headless render to PNG contact sheets |

## Tone

`composite._tone` composes every knob into one 256 entry luminance curve, samples
it per pixel, and re-tints once. The knobs are all functions of luminance alone,
so they compose, and doing it as a lookup keeps `tanh` and `pow` off the image.

`_retint` scales RGB by the luminance ratio to hold hue and saturation, gamut
maps whatever overshoots, and assigns black pixels their target grey outright
since a ratio cannot move them.

Take the peak with pairwise `np.maximum` over channel slices, not
`max(axis=-1)`. Reducing a 3-long trailing axis is strided and an order of
magnitude slower.

## Threshold

`compute_fill_levels` takes the base map's luminance and nothing else. Overlays
go in through `overlay_lum` and `overlay_alpha` so their brightness never reaches
the map's percentiles. Ink polarity can be pinned with `orientation` and should
be whenever the caller knows it, because guessing from the frame mean means the
tone knobs can flip it.

## libcarto threading

The `Renderer` in `carto_ffi.py` is a singleton with one scratch arena and one
style struct. The native side carves its context out of that arena and holds a
live pointer to the style for the whole render, so two threads rendering at once
hand each other overlapping memory. Renders are serialised on `Renderer.lock`,
and style goes through `render_viewport` so it lands under the same lock. Tile
fetching stays outside the lock so a big export does not stall the live map on
network I/O.

`libcarto` has no text rendering. Its primitives are put_px, fill_rect,
draw_line, polyline, fill_polygon and fill_triangle. Anything needing a font goes
through the Python renderer.

## Widgets

Subclass `Widget`, implement `build(width)`, decorate with `@register_widget`.
Use `add_kv`, `add_adjust`, `add_button`, `add_fold`. Click regions come from the
hits the helpers record, so build the row through a helper and the clicking works
on its own.

Panels do not scroll. `Panel.create_content` renders as many rows as the panel is
tall and drops the rest, click targets included, and `body_height` caps at 40. If
a section can make a panel tall, fold it.

## Tests

```
python -m pytest
```

`tests/conftest.py` points `CARTOTUI_CONFIG` and `XDG_CONFIG_HOME` at a temp dir,
so the suite never touches a real config. Ad hoc scripts do not get that, so be
careful running things outside pytest.

Tests that need `libcarto` skip themselves when it is not built. Import
`cartotui.rendering.libcarto_backend` before `carto_ffi`, since the backend is
what puts `bindings/python` on the path.

## The preview harness

Renders settings combinations to labelled PNG contact sheets without a terminal.

```
python tools/preview_harness.py looks
python tools/preview_harness.py tone --theme night
python tools/preview_harness.py themes
python tools/preview_harness.py threshold --theme paper
```

It calls the real pipeline rather than restating it, so what it shows is what the
app does. Keep it that way.
