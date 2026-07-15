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

Coverage is not global. Empty tiles are detected and skipped rather than drawn as
a grey wash.

### Radar does not affect the map's tone

The radar is handed to the renderer as its own layer, not pasted into the map
image. This matters. Precipitation is much brighter than most map themes, and
when it was part of the image its brightness fed the threshold statistics that
decide the map's fill levels. One radar cell redefined what counted as white and
crushed everything around it toward the blank glyph, which showed up as black
holes, worst over open water where there is nothing else to hold the range.

Now the map's tone comes from the map alone, and the radar is blended into the
fill signal across its own intensity range. So it still reads as light or heavy
precipitation, including in mono where the glyph is the only thing carrying
intensity, but it cannot drag the map around it.

## Place labels and boundaries

`N` toggles place names, config key `render.vector_overlay`. Boundaries are
`render.boundaries` with `render.boundary_style` for the look. Both are drawn as
terminal cells after the map is rendered, and boundaries are skipped while
panning to keep it responsive.

## Aircraft

See [ADS-B](ADS-B.md).
