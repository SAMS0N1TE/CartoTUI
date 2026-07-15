# Widgets

Floating panels over the map. `w` opens the launcher. Drag them by the title bar,
`[-]` minimises, `[x]` closes. `Ctrl+S` saves positions so they come back where
you left them.

| Widget | What it does |
| --- | --- |
| `widgets` | The launcher. Show and hide the rest |
| `looks` | The Looks gallery, click to apply |
| `render` | Engine, view, quality, roads, colour, labels, Tone |
| `location` | Where you are, and jump somewhere |
| `compass` | Heading |
| `adsb` | Live aircraft. See [ADS-B](ADS-B.md) |
| `stats` | Frame time, cache, tiles |
| `weather` | Conditions for the map centre |
| `radar` | Precipitation. See [Overlays](Overlays.md) |
| `snapshot` | PNG and HTML export. See [Snapshots](Snapshots.md) |
| `theme` | Pick, edit and save themes. See [Themes](Themes.md) |

## Folded sections

Some panels fold a section away behind a `▸`. Click the header to open it. While
it is closed the header shows a summary of what is inside.

The ADS-B widget folds Display and Declutter. The Render and Themes widgets fold
Tone.

## Rows you can click

- A row ending `▸` cycles or toggles
- A row with `[-] value [+]` steps that value
- A `[ button ]` does the obvious thing

## Render widget

Vector engine, view mode, boundaries, raster tint, pan quality, colour depth and
quality preset. Then road thickness, global and per view mode, with the effective
product shown under them. Then colour, map labels, palette, dither, and Tone.

## Stats widget

Frame time is the useful one. If it climbs, drop `render.vector_scale` or turn on
`dynamic_quality`.
