# Rendering

The map is drawn as an image first, then turned into terminal cells. Everything
on this page is about that second step.

## View modes

Cycle with `m`. Config keys are `render.vector_render_mode` and
`render.raster_render_mode`, kept separately so vector and raster can each stay
in the mode that suits them.

| Mode | Cell | Notes |
| --- | --- | --- |
| `ascii` | 1 glyph | Uses the palette ramp. The only mode dither applies to |
| `quadrant` | 2x2 subpixels | Default for vector. Good detail, still reads as a map |
| `braille` | 2x4 dots | Highest spatial detail. Auto-downgrades to quadrant on raster |
| `half` | 2 stacked pixels | Foreground and background per cell, so the most colour. No glyph ramp at all |

## Palettes

Cycle with `p`. Config key `map.palette`. These are the glyph ramps, darkest to
lightest:

| Name | Ramp |
| --- | --- |
| `shades` | ` ░▒▓█` |
| `blocks` | ` ▁▂▃▄▅▆▇█` |
| `dots` | ` ·∙•●⬤` |
| `hatch` | ` ░▒▓` |
| `ink` | ` ▒█` |
| `topo` | ` ░▒▓█▓▒░ ` |
| `heat` | ` ░▒▓█` |
| `binary` | ` █` |
| `dos` | ` .,:;+=*#%@` |
| `dos5` | ` .+#@` |

The palette drives the ASCII mode. In quadrant and braille it only supplies the
flat-cell glyphs, so switching it there does less than you might expect. In half
mode it does nothing.

## Dither

Cycle with `d`. Config key `render.dither`. Options are `none`, `bayer`,
`atkinson`, `floyd`. ASCII mode only, and it is easier to read with colour off.

## Threshold

Cycle with `u`. Config key `render.subpixel_threshold`. This decides how image
luminance maps onto fill levels.

| Mode | What it does |
| --- | --- |
| `adaptive` | Stretches contrast per tile on a 4x4 grid. Default, and the most forgiving |
| `percentile` | One global stretch. `render.subpixel_percentile` sets the white point |
| `edge` | Sobel edges mixed into the signal. Line-drawing look |
| `fixed` | No stretch at all. Takes the image as it is |

Ink polarity, meaning whether ink lands on the dark parts or the light parts, is
taken from the theme's map background for vector maps. It does not shift when
you change brightness or levels. Raster imagery has no theme polarity, so it is
still guessed from the frame.

## Looks

`l` cycles them, `L` opens the gallery. A Look sets view mode, palette, colour,
dither, threshold, shading and the image adjust knobs in one go, and some of them
also switch theme.

`terminal`, `photo`, `bold`, `classic`, `newsprint`, `blueprint`, `braille`,
`amber_crt`, `matrix`, `paper`, `night`, `hicon`.

Change anything a Look set and the sidebar shows "Custom".

## Quality and speed

| Key | Default | Notes |
| --- | --- | --- |
| `render.vector_engine` | `libcarto` | `libcarto` is the native renderer. `python` is the fallback and can also draw place labels and aircraft into the image |
| `render.vector_scale` | 6 | Supersampling. 3 is fastest, 8 is sharpest |
| `render.dynamic_quality` | true | Drop quality while panning, restore when still |
| `render.color_depth` | `truecolor` | `256` and `16` for terminals that need it |
| `map.max_composite_px` | 1400 | Ceiling on the working image |
| `render.road_thickness` | 1.0 | Multiplied by `road_thickness_by_mode` for the current mode |

## Overlays drawn as cells

Place labels and aircraft are stamped onto the terminal cells after the image is
rendered, not drawn into the image. That keeps them crisp at any map scale. It
also means a plain PNG export does not include them, which is what the `labels`
and `aircraft` options in [Snapshots](Snapshots.md) exist to solve.
