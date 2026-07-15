# Snapshots

`x` saves a PNG. The titlebar has PNG and HTML buttons, and the Snapshot widget
has the full set of options.

Files land in `~/.config/cartotui/snapshots/`, named `cartotui_<date>_<time>.png`.
`snapshot.open_after` opens the folder afterwards.

## Two PNG styles

`snapshot.png_mode`, or Style in the widget.

### map

Re-renders the map at full resolution and saves that. No glyphs, no terminal
grid, just the map. This is the clean high-detail export.

By default it does not include place labels or aircraft, because those are drawn
as terminal cells rather than into the image. Turn them on if you want them:

| Option | Config key | Notes |
| --- | --- | --- |
| City labels | `snapshot.png_labels` | Place names drawn into the image |
| Aircraft | `snapshot.png_aircraft` | Markers and callsigns, same declutter rules as the map |
| Radar | `snapshot.png_radar` | On by default |

Labels and markers scale with the export, so a 4096px PNG gets text sized to
match rather than a speck.

Either option makes the export use the Python renderer, since the native one
cannot draw text. Expect it to take longer. With both off, the export uses the
same renderer as the live map.

### ascii

Saves what the terminal is actually showing. The live frame already carries the
glyph rendering, the place labels, the aircraft and the radar wash, so this mode
needs nothing but a font. If you want the ASCII look with everything on it, this
is the one.

Resolution comes from `snapshot.png_long_side`, and the cell size is worked out
from that, so the same frame can come out as a thumbnail or a poster.

## Size

`snapshot.png_long_side`, or Size in the widget. Presets are 1024 (small), 1600
(medium), 2560 (large) and 4096 (max). Anything from 512 to 6144 is accepted in
the config.

## HTML

Saves the frame as an HTML page with the theme's colours inline. Text, so it is
small and you can select from it. No options.

## Fonts

The ASCII export needs a monospace TTF. CartoTUI looks in the usual Windows,
Debian and macOS locations, then asks `fc-match`, then walks `/usr/share/fonts`.
If there is genuinely no font on the machine it still writes an image, just with
the glyphs missing rather than crashing.
