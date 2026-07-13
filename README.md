# CartoTUI

Interactive map viewer for the terminal with vector or raster tiles rendered as
ASCII, Unicode quadrants, or braille.

## Setup

Windows (PowerShell):

    .\setup.ps1

macOS / Linux:

    ./setup.sh

This makes a `venv`, installs CartoTUI, and builds the native renderer if a C
compiler is present (otherwise the Python renderer is used). Then run:

    python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2081 --lon -71.5376 --zoom 14

## Settings

Edit `config.json` without hunting for the file:

    .\configure.ps1 set ui.theme dark      # Windows
    ./configure.sh set render.vector_scale 8
    ./configure.sh list --flat
    ./configure.sh themes

Same thing as `python -m cartotui.configure ...`.

## Themes

Press `t` in the app to cycle themes, or open the theme widget (see below) to
pick, tweak colours, and save your own. Themes are plain JSON files. Built-ins
live in `cartotui/themes/`; your own go in the themes folder shown by
`configure themes` (typically `%APPDATA%\CartoTUI\themes`). A theme sets the UI
colours plus the map colours (water, roads, city labels, aircraft). Set a few
colours and the rest are derived, or override any UI class directly.

## Rendering

`m` cycles the view: `ascii`, `quad`, `braille`, and `pixel`. Pixel mode uses
half-block characters for a clean full-colour map with no ASCII glyphs or
dither — the closest to the raw tile. To make vector always start in pixel mode:

    ./configure.sh set render.vector_render_mode half

Turn on road highlighting (fatter, brighter roads, muted fills) from the Render
widget, or:

    ./configure.sh set render.road_highlight true

Raster (real map imagery) can be recoloured to match the active theme with the
raster tint (Render widget → Raster, or `set render.raster_tint theme`).

**Dynamic panning quality** (Render widget → Pan quality, on by default) keeps
raster panning responsive: while you pan it uses only already-cached tiles
(blurry-but-visible, never blank), skips the sharpen pass, and prefetches the
real tiles in the background, then reloads full quality when you stop — like a
web map. Turn it off with `set render.dynamic_quality false`.

## Snapshots

Click `[PNG]` or `[HTML]` in the top-right of the title bar, press `x` for a PNG,
or use the Snapshot widget. PNG is a high-resolution re-render of the current
view (pick the size — small/medium/large/max — in the Snapshot widget); HTML is
the exact terminal frame with inline CSS. Files land in the `snapshots` folder
next to the config, and the folder opens automatically after saving (toggle with
`set snapshot.open_after false`).

## Profiles

Save the whole current setup — view, zoom, theme, palette, image adjustments,
render mode, overlays, and panel layout — with `Ctrl-S` or the *Save profile*
button in the widgets launcher. It writes to `config.json` and loads on next
start.

## Themes and presets

Press `t` to cycle, or open the Themes widget to pick, tweak colours, and adjust
a live **preset** (brightness, contrast, dither, palette, view mode, road
highlight, raster tint). *Save preset to this theme* overwrites it, *Save as new
theme* copies it, *Delete* removes a custom one. Selecting a theme restores its
saved preset. Themes are plain JSON in `cartotui/themes/` (built-in) and the user
themes folder shown by `configure themes`.

## Overlays

The Radar widget draws live weather radar over the map (RainViewer, free, no
key). Toggle it, set opacity, pick the latest frame or the short-term nowcast,
and turn on **Animate** to loop through the last ~2 hours (plus nowcast when
available). It refreshes automatically and composites onto both vector and raster
maps, and into snapshots. RainViewer radar tops out at zoom 7, so higher zooms
are upscaled. Enable without the widget via `set overlays.radar.enabled true`
(`animate`, `frame_interval` also configurable).

## Widgets

Press `w` for the widgets launcher. Panels — Render, Location, Compass, ADS-B,
Stats, Weather, Radar, Themes, and any you add — float over the map. Drag them by
the title bar, `[-]` minimises, `[x]` hides, and the layout is saved. The right
sidebar minimises the same way. Add your own by subclassing `Widget` in
`cartotui/ui/widgets/` and decorating it with `@register_widget`.

## Documentation

Full documentation is in the [wiki](https://github.com/SAMS0N1TE/CartoTUI/wiki).

<p align="center">
  <img width="49%" src="https://github.com/user-attachments/assets/d4b078d6-095f-4f21-92f9-066e885df719" />
  <img width="49%" src="https://github.com/user-attachments/assets/318162b9-c315-4858-8f13-01598ef0088b" />
</p>
<p align="center">
  <img width="49%" src="https://github.com/user-attachments/assets/c1b00a1a-e567-4e4e-b2be-e183d97b03dd" />
  <img width="49%" src="https://github.com/user-attachments/assets/6c9655b4-73f0-4898-a193-355df6d324b4" />
</p>

<img width="2378" height="1353" alt="TUI4" src="https://github.com/user-attachments/assets/28798b99-3298-498c-829c-5dae81bf51f8" />


---
[License](LICENSE)
