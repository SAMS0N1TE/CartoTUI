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
| `stable` | Default for new configurations. Bounded local contrast at two sample scales; fixed coverage decisions independent of viewport percentiles |
| `adaptive` | Legacy contrast stretch per tile on a 4x4 grid |
| `percentile` | One global stretch. `render.subpixel_percentile` sets the white point |
| `edge` | Sobel edges mixed into the signal. Line-drawing look |
| `fixed` | No stretch at all. Takes the image as it is |

Ink polarity, meaning whether ink lands on the dark parts or the light parts, is
taken from the theme's map background on vector maps, so the image adjust knobs
never flip it. Raster imagery has no theme behind it, so polarity is read from
the frame.

## Looks

`l` cycles them, `L` opens the gallery. A Look sets view mode, palette, colour,
dither, threshold, shading and the image adjust knobs in one go, and some of them
also switch theme.

`terminal`, `photo`, `bold`, `classic`, `newsprint`, `blueprint`, `braille`,
`amber_crt`, `matrix`, `paper`, `night`, `hicon`.

Change anything a Look set and the Looks page shows "Custom".

## Quality and speed

| Key | Default | Notes |
| --- | --- | --- |
| `render.vector_engine` | `libcarto` | `libcarto` is the native renderer. `python` is the fallback and can also draw place labels and aircraft into the image |
| `render.vector_scale` | 6 | Supersampling. 3 is fastest, 8 is sharpest |
| `render.dynamic_quality` | true | Drop quality while panning, restore when still |
| `render.color_depth` | `auto` | Uses terminal capabilities; explicit `truecolor`, `256` or `16` remain available |
| `map.max_composite_px` | 1400 | Ceiling on the working image |
| `render.road_thickness` | 1.0 | Multiplied by `road_thickness_by_mode` for the current mode |

## Overlays drawn as cells

Place labels and aircraft are drawn onto the terminal cells rather than into the
map image, which keeps them sharp at any map scale. A `map` PNG export is the
image, so it does not carry them unless you ask for them. See
[Snapshots](Snapshots.md).

## Stable detail and SSH output

Stable detail uses fixed, bounded contrast enhancement in a two-sample radius.
It preserves broad regions with a smooth tone curve and enhances nearby thin
features without stretching tiny noise differences to full intensity. Quadrant
and braille coverage is chosen before palette reduction, rather than comparing
each subpixel to its own cell average. Distant bright objects cannot change a
feature's threshold. Resampling, actual feature size and tone adjustments can
still change its appearance as you zoom; this is not semantic road recognition.

Existing profiles keep their selected threshold. Choose **Map appearance > Detail
> stable** or apply the Terminal Look to try the new mapping. Legacy modes remain
available. Updated libcarto runs it natively; older shared libraries fall back to
Python safely. Half mode bypasses thresholding entirely.

Both terminal output paths use ordinary text and ANSI colours: no graphics
protocol, GUI or local display server is required on the remote host. With
`render.direct_paint=true`, map rows are sent only when changed; layout changes
force repainting so closing a menu exposes the map correctly. The painter resets
inherited text attributes and honours the selected colour depth. `auto` follows
the terminal; `256` is a useful explicit choice for SSH connections.
# Windows Terminal half-block colours

If half mode shows bright gray or white blocks along low-contrast edges, check
Windows Terminal's profile appearance setting `adjustIndistinguishableColors`.
Set it to `never` for map rendering: automatic text contrast enhancement changes
the foreground half of an image cell. This is a client-side setting and also
applies when CartoTUI runs over SSH in that terminal profile.

Dynamic pan quality reduces vector raster resolution during movement and restores
the configured quality once movement settles. Tile size scales with the raster,
so the map keeps the same geographic extent throughout.
