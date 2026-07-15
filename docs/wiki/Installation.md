# Installation

## Setup script

Windows:

```
.\setup.ps1
```

macOS and Linux:

```
./setup.sh
```

It makes a `venv`, installs CartoTUI, builds the native renderer if a C compiler
is there, and then offers to set up ADS-B. Skip that last part with `--skip-adsb`
(`-SkipAdsb` on Windows).

## Running

```
python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2081 --lon -71.5376 --zoom 14
```

The `--mvt-url` only needs to be there once. It is written to the config.

Vector tile sources:

| Source | Flag |
| --- | --- |
| Any raw MVT endpoint | `--mvt-url "https://host/{z}/{x}/{y}"` |
| A `.pmtiles` archive over HTTP | `--pmtiles-url URL` |
| Protomaps API | `--protomaps-key KEY` |

Raster tiles need no key. `k` cycles OSM, Topo, Humanitarian, Positron,
DarkMatter, Voyager and Protomaps.

## The native renderer

`libcarto` is a small C renderer for vector tiles. The setup script builds it if
it can. To do it by hand:

```
cmake -S libcarto -B libcarto/build
cmake --build libcarto/build
```

That produces `libcarto/build/libcarto.so`, or `carto.dll` on Windows and
`libcarto.dylib` on macOS. CartoTUI finds it there on its own.

Without it, the Python renderer takes over and everything still works, just
slower. Check which one you are on in the Render widget, or:

```
python -c "from cartotui.rendering.libcarto_backend import available; print(available())"
```

The Python renderer is not only a fallback. It is the one that can draw place
labels and aircraft into an image, which `libcarto` cannot do at all, so PNG
exports with those options switch to it. See [Snapshots](Snapshots.md).

## Terminal

Wants 24-bit colour and a font with block and braille glyphs. DejaVu Sans Mono,
Cascadia Mono and JetBrains Mono all work. If colours look wrong, set
`render.color_depth` to `256` or `16`.

Mouse support needs a terminal that reports it. It is on by default, `ui.mouse`
turns it off.

## Requirements

Python 3.9 or newer. `pillow`, `numpy`, `prompt_toolkit`, `requests`. A C
compiler and CMake are optional and only for `libcarto`.
