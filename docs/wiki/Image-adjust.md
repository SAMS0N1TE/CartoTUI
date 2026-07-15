# Image adjust

Six knobs that shape the map image before it becomes terminal cells. They live
on keys, in the Render widget under Tone, and in the Themes widget so a theme can
carry them as a preset.

All of them work on luminance and then put the colour back by scaling the
channels. Nothing is ever blended toward grey, so pulling contrast down flattens
tone without draining colour out of the map.

| Knob | Keys | Range | Default |
| --- | --- | --- | --- |
| Brightness | `[` `]` | 0.2 to 3.0 | 1.0 |
| Contrast | `{` `}` | 0.2 to 3.0 | 1.05 |
| Gamma | `(` `)` | 0.2 to 3.0 | 1.0 |
| Saturation | `<` `>` | 0.0 to 3.0 | 1.0 |
| Black point | `;` `:` | 0.0 to 0.9 | 0.0 |
| White point | `'` `"` | 0.1 to 1.0 | 1.0 |

`\` resets all six.

## Which knob for which problem

**This theme is too dark.** Raise the black point. It sets a floor on the
rendered range, so nothing sits at pure black any more. On the night theme
`black_point 0.25` moves mean luminance from 0.16 to 0.37 with the colour intact
and nothing clipped.

Brightness is the wrong tool here. It is a multiply, and multiplying near-black
by anything is still near-black, which is why it barely moves a dark theme until
it suddenly blows out.

**This theme is too bright.** Lower the white point. It sets a ceiling. On the
paper theme `white_point 0.6` takes mean luminance from 0.69 to 0.41, again with
colour intact and no clipping.

Brightness is wrong here too. Brightening something already near white can only
push it to white, and white has no colour in it.

**The colour is washed out or too loud.** Saturation. It scales chroma and leaves
tone alone.

**The midtones sit wrong.** Gamma.

**The image is flat, or too harsh.** Contrast. It pivots on the frame's own mean,
so it spreads the histogram in place rather than dragging the whole map darker.

## Black point and white point

These are output levels, not input levels. Black point is the darkest the map is
allowed to be, white point is the brightest. Compressing a range cannot clip, so
these two are the safe way to move a theme's overall level.

They cannot cross. Pushing the floor up stops 0.05 below the ceiling.

A pure black pixel has no colour to scale, so a raised black point gives it a
grey outright. That is what lets the floor lift themes with a `#000000`
background, night and hicon and ega among them.

## Why brightness does not clip any more

Brightness gain runs into a soft shoulder that bends toward white instead of
hitting it. Where a colour still lands outside the gamut, the pixel is
desaturated just enough to fit while its luminance is kept. That reads as a
highlight rolling off rather than a channel slamming into its limit, and hue
survives: a saturated red at brightness 2.5 comes out pale, but still red rather
than orange.

There is a limit to this. Brightening a light theme toward white will always lose
saturation, because at that luminance the gamut has nowhere to put it. Use the
white point instead.

## Themes can carry these

The Themes widget has a Tone section and a "Save preset to this theme" button.
That writes all six values into the theme's JSON `render` block, and they load
with the theme. Looks set them too.

## Cost

The tone pass costs roughly 9ms on a 640x384 image. Neutral settings skip the
whole thing. The default config ships `contrast: 1.05`, so it does run on a
normal frame.
