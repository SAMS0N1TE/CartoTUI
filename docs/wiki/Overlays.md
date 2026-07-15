# Overlays

## Weather radar

Precipitation from RainViewer, composited over the map. Off by default. The Radar
widget turns it on, or set `overlays.radar.enabled`.

| Key | Default | Notes |
| --- | --- | --- |
| `enabled` | false | |
| `opacity` | 0.65 | |
| `color` | 4 | RainViewer colour scheme |
| `smooth` `snow` | 1 | Smoothing, and snow shown separately |
| `frame` | `latest` | Or `nowcast` for the forecast frames |
| `animate` | false | Loop through past and nowcast frames |
| `frame_interval` | 0.6 | Seconds per frame while animating |
| `refresh_interval_s` | 120 | How often to look for new frames |

Radar tiles are fetched in the background and cached. The status bar shows the
count while they load. Animation prefetches every frame for the viewport, so the
first loop is slower than the rest.

Coverage is not global. Areas with no data are skipped rather than drawn as a
grey wash.

Precipitation keeps its light-to-heavy range with colour off too, where the glyph
carries the intensity instead.

## Place labels and boundaries

`N` toggles place names, config key `render.vector_overlay`. Boundaries are
`render.boundaries` with `render.boundary_style` for the look. Both are drawn as
terminal cells after the map is rendered, and boundaries are skipped while
panning to keep it responsive.

## Aircraft

See [ADS-B](ADS-B.md).
