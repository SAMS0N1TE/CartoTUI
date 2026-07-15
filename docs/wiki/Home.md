# CartoTUI

An interactive map viewer that runs in a terminal. It fetches vector or raster
map tiles and draws them with ASCII characters, Unicode quadrant blocks, braille
dots, or half blocks. It can overlay live aircraft from ADS-B and precipitation
radar on top.

## Quick start

```
./setup.sh                                  # or .\setup.ps1 on Windows
python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2081 --lon -71.5376 --zoom 14
```

Press `h` for help, `l` to cycle through visual presets, `q` to quit.

## Pages

| Page | What is in it |
| --- | --- |
| [Installation](Installation.md) | Setup scripts, the native renderer, where files live |
| [Keybindings](Keybindings.md) | Every key |
| [Rendering](Rendering.md) | View modes, palettes, dither, thresholds, Looks |
| [Image adjust](Image-adjust.md) | Brightness, contrast, gamma, saturation, levels |
| [Themes](Themes.md) | Built-in themes and writing your own |
| [Configuration](Configuration.md) | Everything in config.json |
| [ADS-B](ADS-B.md) | Live aircraft, sources, receivers |
| [Overlays](Overlays.md) | Weather radar |
| [Widgets](Widgets.md) | The floating panels |
| [Snapshots](Snapshots.md) | PNG and HTML export |
| [Troubleshooting](Troubleshooting.md) | When something is wrong |
| [Architecture](Architecture.md) | How the code fits together |

## What it needs

Python 3.9 or newer, a terminal that can do 24-bit colour, and a font with
Unicode block and braille glyphs. Truecolor is not required, and 256 or 16
colour modes are available in the config.

A C compiler is optional. If one is present the setup script builds `libcarto`,
a native renderer that draws vector tiles a lot faster than the Python path.
Without it everything still works, just slower.

## Where CartoTUI keeps things

On Linux:

| What | Where |
| --- | --- |
| Config | `~/.config/cartotui/config.json` |
| Your themes | `~/.config/cartotui/themes/` |
| Snapshots | `~/.config/cartotui/snapshots/` |
| Log | `~/.local/state/cartotui/cartotui.log` |

`XDG_CONFIG_HOME` and `XDG_STATE_HOME` are respected. `CARTOTUI_CONFIG` overrides
the config path outright. macOS uses `~/Library/Application Support/CartoTUI` and
`~/Library/Logs/CartoTUI`. Windows uses `%APPDATA%\CartoTUI` and
`%LOCALAPPDATA%\CartoTUI\Logs`.
