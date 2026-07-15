# Image adjust

Six knobs that shape the map image before it becomes terminal cells. They live
on keys, in the Render widget under Tone, and in the Themes widget so a theme can
carry them as a preset.

They all keep the colour where they find it. Pulling contrast down flattens the
tone without washing the map out to grey.

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

**This theme is too dark.** Raise the black point. It lifts the floor of the
rendered range, so the darkest parts of the map sit at a grey instead of black.
Colour is kept and nothing clips.

Reach for this before brightness. Brightness scales what is there, and scaling
near-black leaves it near-black, so it does little on a dark theme until it
suddenly washes out.

**This theme is too bright.** Lower the white point. It drops the ceiling, so
nothing reaches full white. Again the colour is kept and nothing clips.

Brightness will not help here either. Pushing an already light theme up can only
take it to white, and white holds no colour.

**The colour is washed out or too loud.** Saturation. It scales colour and leaves
tone alone.

**The midtones sit wrong.** Gamma.

**The image is flat, or too harsh.** Contrast. It pivots on the frame's own
average, so it spreads the range in place rather than dragging the whole map
darker or lighter.

## Black point and white point

Black point is the darkest the map is allowed to be. White point is the
brightest. They set the range the map occupies, rather than stretching what is
already in it, so they cannot clip. That makes them the safe way to move a
theme's overall level.

They cannot cross. Pushing the floor up stops just below the ceiling.

Both work on themes with a pure black background, night and hicon and ega
included.

## Themes can carry these

The Themes widget has a Tone section and a "Save preset to this theme" button.
That writes all six values into the theme's JSON `render` block, and they load
with the theme. Looks set them too.

## Cost

Leave all six at their neutral values and the pass is skipped. The default config
ships `contrast` at 1.05, so it does run on a normal frame. `\` sets everything
neutral, which is worth a few ms a frame if you are chasing speed.
