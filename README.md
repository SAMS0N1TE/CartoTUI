# CartoTUI

Interactive map viewer for the terminal — vector or raster tiles rendered as
ASCII, Unicode quadrants, or braille, in retro nav-system aesthetics.

<img width="1038" height="794" alt="TUI3" src="https://github.com/user-attachments/assets/ee1271b7-6814-459e-b0bf-3286adb5d288" />
<img width="1045" height="802" alt="TUI2" src="https://github.com/user-attachments/assets/856f9ad5-f42d-4c69-88d6-f1e4d9d7449b" />

## What it does

CartoTUI fetches map tiles, draws them into the terminal, and lets you pan
and zoom around with keyboard or mouse. Two ways tiles get drawn:

* **Vector mode** — pulls vector tiles (Mapbox MVT, raw or wrapped in
  PMTiles), rasterises them at high resolution with proper road class
  hierarchy / water polygons / place labels, then converts to terminal
  characters. The old-Garmin / TomTom look — bold roads, dark water,
  readable city names.
* **Raster mode** — fetches PNG tiles from any standard `{z}/{x}/{y}` source
  (OSM, OpenTopoMap, CARTO basemaps, etc) and converts them via the unified
  threshold pipeline.

Either source renders through three terminal backends: ASCII, Unicode
quadrants (`▘▝▖▗▀▄▌▐▙▟▚▞▛▜█`), or braille (`⠿⣿`).

<img width="535" height="405" alt="TUI1" src="https://github.com/user-attachments/assets/5feb8962-b54b-414c-a67b-ef123549662e" />

## Install

```bash
git clone https://github.com/SAMS0N1TE/CartoTUI.git
cd CartoTUI
pip install -e .
cartotui
```

Or without installing:

```bash
pip install -r requirements.txt
python -m cartotui
```

Requires Python 3.9+.

## Quick start

CartoTUI defaults to vector mode and looks for a vector tile source. Three
ways to provide one:

### Protomaps API (easiest, no setup)

[Sign up](https://protomaps.com/api) for a free Protomaps API key:

```bash
cartotui --protomaps-key YOUR_KEY --lat 53.3498 --lon -6.2603 --zoom 12
```

### A self-hosted PMTiles archive

```bash
cartotui --pmtiles-url https://your.cdn/your_basemap.pmtiles
```

### Any raw MVT tile URL

```bash
cartotui --mvt-url 'https://your.tiles/{z}/{x}/{y}.mvt'
```

### Pure raster (no vector tiles needed)

```bash
cartotui --mode quadrant     # raster source, quadrant backend
```

Once running, press `k` to cycle through built-in raster basemap styles
(OSM standard, OpenTopoMap, OSM Humanitarian, CARTO Positron, CARTO Dark
Matter, CARTO Voyager) plus Protomaps vector if a key is configured.

## Key bindings

| Action                          | Key                               |
|---------------------------------|-----------------------------------|
| Pan                             | `↑ ↓ ← →` (or mouse drag)         |
| Pan ×4                          | `Shift + ↑ ↓ ← →`                 |
| Recentre on click               | Mouse click                       |
| Zoom                            | `+ / -`, mouse wheel              |
| Jump to zoom 0–9                | `0 … 9`                           |
| **Cycle map style**             | `k`                               |
| Toggle source kind              | `v` (vector ↔ raster)             |
| Cycle render backend            | `m` (ascii → quadrant → braille)  |
| Cycle theme                     | `t` (amber/green/paper/...)       |
| Cycle palette                   | `p`                               |
| Cycle dither                    | `d` (ascii view only)             |
| Toggle shaded blocks            | `s` (quadrant/braille only)       |
| Toggle colour                   | `c`                               |
| **Cycle threshold mode**        | `u` (percentile/edge/fixed)       |
| **Brightness − / +**            | `[` / `]`                         |
| **Contrast − / +**              | `{` / `}`                         |
| **Reset image adjust**          | `\`                               |
| Goto `lat, lon[, zoom]`         | `g`                               |
| Reset to home                   | `r`                               |
| Help                            | `h` or `?`                        |
| Quit                            | `q` or `Ctrl-C`                   |

The toolbar's bracketed-letter buttons fire the same handlers as their key
equivalents. Items that don't apply to the current state (e.g. `[D] Dith`
when not in ASCII view) are greyed out; clicking them shows an info message
explaining why.

## Threshold modes

Three strategies for converting image luminance to "filled" sub-pixels:

* **`percentile`** (default) — picks a brightness boundary from the image's
  histogram. Auto-detects whether features are darker or brighter than the
  background. Best for typical maps.
* **`edge`** — uses Sobel-style local contrast instead of pure brightness.
  Best when features are thin against a uniform background (e.g. zoomed-out
  view of mostly-cream OSM tiles, or vector renders with sparse roads). If
  you ever see large regions render as solid black/empty, switch to this.
* **`fixed`** — hard 0.5 luminance cutoff. The pre-v0.7 behaviour.

Cycle at runtime with `u`. The status bar shows the current mode.

## Themes

| Theme    | Look                                                       |
|----------|------------------------------------------------------------|
| `amber`  | Amber-on-black CRT, like an old Garmin (default)           |
| `green`  | Green phosphor, like a Magellan or first-gen TomTom        |
| `paper`  | Black ink on cream paper for daytime use                   |
| `retro`  | The old v0.6 retro theme                                   |
| `dark`   | Neutral dark                                               |
| `light`  | Neutral light                                              |

Cycle through them at runtime with `t`.

## Render modes & palettes

The renderer turns an image into terminal characters by mapping luminance
(and optionally local contrast) to glyph density.

| Backend    | Resolution per cell | Note                                         |
|------------|---------------------|----------------------------------------------|
| `ascii`    | 1×1                 | Glyph picked from palette by luminance       |
| `quadrant` | 2×2                 | Unicode block elements `▘▝▖▗▀▄▌▐█▙▟▚▞▛▜`     |
| `braille`  | 2×4                 | Densest detail; eight sub-pixels per cell    |

In v0.8, **palette length drives sub-pixel density** in all three backends.
A 5-step palette like `shades` produces 5× more visual range in
quadrant/braille mode than the old 1-bit behaviour.

Default palettes (cycle with `p`):

* `shades` — ` ░▒▓█` (the readable default)
* `blocks` — ` ▁▂▃▄▅▆▇█` (8-step gradient)
* `dots` — ` ·∙•●⬤` (sparse to dense circles)
* `hatch` — ` ░▒▓` (3-step crosshatch)
* `ink` — ` ▒█` (high contrast, 2-step)
* `topo` — ` ░▒▓█▓▒░ ` (palindromic for "altitude" feel)
* `heat` — same as `shades` but reads as a density map
* `binary` — ` █` (pure 2-level)

For dense glyph fills in quadrant/braille at small palettes, **shaded blocks**
mode (`s`) replaces heavy-fill cells with palette glyphs for richer tonal
range without losing detail.

## Map sources

Built-in registry of basemaps cyclable at runtime with `[K]`:

| Source        | Kind   | Style                                          |
|---------------|--------|------------------------------------------------|
| OSM           | raster | OpenStreetMap standard                         |
| Topo          | raster | OpenTopoMap (terrain shading)                  |
| Humanitarian  | raster | OSM HOT — high-contrast roads                  |
| Positron      | raster | CARTO Positron — light, minimal                |
| DarkMatter    | raster | CARTO Dark Matter — dark with bright roads     |
| Voyager       | raster | CARTO Voyager — warm, balanced                 |
| Protomaps     | vector | Protomaps hosted vector (needs API key)        |

Add custom sources via `vector.custom_sources` in config:

```json
{
  "vector": {
    "custom_sources": [
      {
        "name": "MyTiles",
        "kind": "raster",
        "url_template": "https://tiles.example.com/{z}/{x}/{y}.png",
        "attribution": "© Me"
      }
    ]
  }
}
```

## Configuration

A JSON file is created on first run.

| OS      | Path                                           |
|---------|------------------------------------------------|
| Linux   | `~/.config/cartotui/config.json`               |
| macOS   | `~/Library/Application Support/CartoTUI/config.json` |
| Windows | `%APPDATA%\CartoTUI\config.json`               |

Override with `--config path/to/config.json` or `CARTOTUI_CONFIG=...`.

Key sections:

```json
{
  "map": {
    "center_lat": 53.3498, "center_lon": -6.2603, "zoom": 12,
    "mode": "vector"
  },
  "vector": {
    "source": "protomaps_api",
    "protomaps_api_key": "your-key-here"
  },
  "render": {
    "color": true, "dither": "none",
    "subpixel_threshold": "percentile",
    "subpixel_percentile": 55,
    "shaded_blocks": false,
    "brightness": 1.0, "contrast": 1.05
  },
  "ui": { "theme": "amber", "pan_step_cells": 6 }
}
```

`subpixel_threshold` accepts `fixed`, `percentile`, or `edge`.

## Tile providers

Default raster source is OpenStreetMap. Please respect their
[tile usage policy](https://operations.osmfoundation.org/policies/tiles/) —
set a meaningful `network.user_agent`, don't hammer the service, and consider
self-hosting or using a commercial provider for heavy use.

For vector tiles, recommended free options are Protomaps (hosted API or
self-hosted PMTiles archives). See [protomaps.com](https://protomaps.com/).

## Development

```bash
pip install -e ".[dev]"
pytest               # 71 tests
ruff check .
```

## License

[MIT](LICENSE).

