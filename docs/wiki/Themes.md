# Themes

`t` cycles them. The Themes widget lists them all and can edit colours live.

| Theme | Look |
| --- | --- |
| `amber` | Amber phosphor on near black. Default |
| `green` | Green phosphor |
| `retro` | Warm amber, heavier |
| `dark` | Neutral dark, blue accents |
| `night` | Red on black, dark adapted |
| `paper` | Printed atlas, ink on cream |
| `light` | Clean light, blue accents |
| `hicon` | Yellow on black, maximum contrast |
| `ega` | 16 colour EGA palette |
| `win31` | Windows 3.1 grey and navy |

## Theme files

Built-ins live in `cartotui/themes/`. Yours go in `~/.config/cartotui/themes/`
and a file there overrides a built-in of the same name.

```json
{
  "name": "mytheme",
  "border": "ascii",
  "ui": {
    "bg": "#04120a", "fg": "#5ec46e", "dim": "#2f6b3c",
    "accent": "#7dffa0", "key": "#7dffa0", "section": "#7dffa0",
    "border": "#245030", "panel_bg": "#07190e",
    "title_bg": "#0c2716", "title_fg": "#9dffb8",
    "sel_bg": "#12401f", "sel_fg": "#c8ffd4",
    "warn": "#ffcc00", "ok": "#7dffa0"
  },
  "map": {
    "bg": "#04120a", "water": "#164a60", "park": "#1d3322",
    "building": "#2b3a38", "road": "#7dffa0",
    "roads": { "motorway": "#c8ffd4", "primary": "#9dffb8" },
    "label": "#9dffb8", "halo": "#04120a",
    "aircraft": "#7dffa0", "aircraft_selected": "#ffffff",
    "aircraft_emergency": "#ff5050"
  }
}
```

`ui` is the chrome. `map` is what gets rasterised. Anything you leave out falls
back to a sensible default, so a partial theme is fine.

`map.bg` does more than set a colour. Ink polarity is read from it, so a light
`bg` tells the renderer this is ink on paper and a dark one tells it the opposite.
Get it wrong and the map comes out inverted.

## Optional render block

A theme can carry render settings and image adjust values:

```json
"render": {
  "brightness": 1.0, "contrast": 1.05, "gamma": 1.0,
  "saturation": 1.2, "black_point": 0.08, "white_point": 0.92,
  "dither": "none", "palette": "shades", "view": "quadrant",
  "road_highlight": false, "raster_tint": "none",
  "road_thickness": 1.0
}
```

These load with the theme. The Themes widget writes this block for you: set the
Tone knobs how you want and press "Save preset to this theme".

## Editing in the app

The Themes widget has a colour row per field. Click to cycle a colour, use the
Tone section for image adjust, then:

- **Save preset to this theme** writes the render block
- **Save as new theme** copies it to a new file in your themes folder
- **Delete this theme** only appears for themes you own

Theme colour overrides also live in `config.json` under `theme.chrome` and
`theme.road_colors` if you want to tweak without touching a theme file.
