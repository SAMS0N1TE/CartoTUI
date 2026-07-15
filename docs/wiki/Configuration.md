# Configuration

Config lives at `~/.config/cartotui/config.json`. `CARTOTUI_CONFIG` overrides the
path. Every value is range checked on load, and anything invalid quietly falls
back to its default rather than breaking the app.

Edit it without hunting for the file:

```
./configure.sh set ui.theme dark
./configure.sh set render.vector_scale 8
./configure.sh list --flat
./configure.sh themes
```

`Ctrl+S` in the app saves the current view and panel layout back to the config.

## map

| Key | Default | Notes |
| --- | --- | --- |
| `center_lat` `center_lon` | 42.3601, -71.0589 | Start position |
| `zoom` | 4 | 0 to 19 |
| `min_zoom` `max_zoom` | 0, 19 | |
| `mode` | `vector` | Or a raster view mode |
| `palette` | `shades` | |
| `overzoom` | 2 | Levels a raster tile may be stretched |
| `max_composite_px` | 1400 | Ceiling on the working image |

## render

Covered in [Rendering](Rendering.md) and [Image adjust](Image-adjust.md).

| Key | Default |
| --- | --- |
| `color` | true |
| `dither` | `none` |
| `brightness` `contrast` `gamma` | 1.0, 1.05, 1.0 |
| `saturation` | 1.0 |
| `black_point` `white_point` | 0.0, 1.0 |
| `sharpen_percent` `sharpen_radius` `sharpen_threshold` | 150, 1.5, 3 |
| `edge_boost` `invert` | false |
| `subpixel_threshold` | `adaptive` |
| `subpixel_percentile` | 55 |
| `shaded_blocks` | false |
| `vector_overlay` | true (place names, `N` toggles it) |
| `boundaries` | true |
| `boundary_style` | `dots` |
| `vector_engine` | `libcarto` |
| `vector_scale` | 6 |
| `vector_render_mode` | `quadrant` |
| `raster_render_mode` | `ascii` |
| `road_thickness` | 1.0 |
| `road_thickness_by_mode` | ascii 0.6, others 1.0 |
| `road_highlight` | false |
| `raster_tint` | `none`, or `theme` to recolour raster into the theme |
| `dynamic_quality` | true |
| `color_depth` | `truecolor`, `256`, `16` |

## aircraft

See [ADS-B](ADS-B.md).

| Key | Default |
| --- | --- |
| `label_mode` | `smart` |
| `marker_style` | `arrow` |
| `marker_size` | `normal` |
| `max_shown` | 150, 0 for all |
| `altitude_colors` `legend` | true |
| `dead_reckoning` `predict_track` | true |
| `predict_seconds` | 60 |
| `highlight_interesting` | true |
| `hide_ground` | false |
| `min_altitude` `max_altitude` | 0, 0 (no limit) |

`aircraft_trails.enabled` is true and `aircraft_trails.duration_s` is 60, from 5
to 600.

## traffic

| Key | Default |
| --- | --- |
| `enabled` | false |
| `source` | `disabled` |
| `stale_timeout_s` | 60 |
| `api.provider` | `airplanes.live` |
| `api.radius_nm` | 100, up to 250 |
| `api.interval_s` | 5.0, from 0.5, but a provider floor still applies |
| `api.follow_map` `api.follow_zoom` | true |
| `sbs1.host` `sbs1.port` | localhost, 30003 |
| `replay.path` `replay.speed` `replay.loop` | "", 1.0, true |
| `record.enabled` `record.path` `record.interval_s` | false, "", 1.0 |

## overlays.radar

See [Overlays](Overlays.md).

| Key | Default |
| --- | --- |
| `enabled` | false |
| `opacity` | 0.65 |
| `color` | 4 |
| `smooth` `snow` | 1 |
| `frame` | `latest` |
| `animate` | false |
| `frame_interval` | 0.6 |
| `refresh_interval_s` | 120 |

## snapshot

See [Snapshots](Snapshots.md).

| Key | Default |
| --- | --- |
| `png_mode` | `map`, or `ascii` |
| `png_long_side` | 1600, from 512 to 6144 |
| `png_labels` `png_aircraft` | false |
| `png_radar` | true |
| `open_after` | true |

## ui, viewport, network, cache

| Key | Default | Notes |
| --- | --- | --- |
| `ui.theme` | `amber` | |
| `ui.max_fps` | 30 | 5 to 120 |
| `ui.mouse` | true | |
| `ui.panels` | [] | Written by `Ctrl+S` |
| `viewport.sidebar_width` | 36 | |
| `viewport.crosshair` | true | |
| `network.tile_url` | OSM | Raster tiles |
| `network.user_agent` | | Sent to every server |
| `network.parallel_downloads` | 8 | |
| `cache.dir` | under the config folder | |
| `cache.max_bytes` | 256MB | |
| `logging.level` | `INFO` | |
| `logging.file` | null | null for the default path, "" to turn logging off |

## CLI

Command line beats config for the run.

```
python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2 --lon -71.5 --zoom 14
```

| Flag | Notes |
| --- | --- |
| `--config PATH` | |
| `--lat` `--lon` `--zoom` | |
| `--mode` | vector, ascii, quadrant, braille, half |
| `--palette` `--theme` | |
| `--no-color` | |
| `--mvt-url URL` | Raw MVT template, sets `vector.source=mvt_url` |
| `--pmtiles-url URL` | Sets `vector.source=pmtiles_url` |
| `--protomaps-key KEY` | Sets `vector.source=protomaps_api` |
| `--print-config` | Print the resolved config and exit |
