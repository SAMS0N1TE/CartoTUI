# Troubleshooting

## The log

```
~/.local/state/cartotui/cartotui.log
```

macOS `~/Library/Logs/CartoTUI/`, Windows `%LOCALAPPDATA%\CartoTUI\Logs\`.

Turn up the detail with `logging.level` set to `DEBUG`. Set `logging.file` to
`""` to stop logging, or to a path to put it somewhere else.

## The map is blank

Look for this:

```
rasterise_view: 0 tiles loaded for view at z=15 ...
```

The vector source is returning nothing. Check the URL, the network, and the API
key if the source needs one. `--print-config` shows what CartoTUI actually
resolved.

## The map looks inverted

Ink is landing on the wrong side. For vector maps polarity comes from the theme's
`map.bg`, so a light theme with a dark `bg` set will come out backwards. For
raster it is guessed from the frame, and heavily adjusted imagery can fool the
guess.

## Brightness blows the map out to white

Lower the white point instead of raising brightness. See [Image
adjust](Image-adjust.md).

## It quit with nothing in the log

A native crash in `libcarto` leaves no Python traceback. On Linux with systemd:

```
coredumpctl list --since "-1 hour"
coredumpctl info <pid>
```

A stack with `carto_*` frames in it confirms the renderer. Switch to the Python
one:

```
./configure.sh set render.vector_engine python
```

## Slow

- Drop `render.vector_scale` to 3 or 4
- Make sure `render.dynamic_quality` is true
- Check `libcarto` is actually built, the Python renderer is a lot slower
- Lower `map.max_composite_px`
- Frame time is in the Stats widget

## No aircraft

```
./configure.sh adsb --test
```

Then check `traffic.enabled` is true and `traffic.source` is not `disabled`. The
ADS-B widget's Link section shows connected or offline and a message rate. If the
rate is above zero but nothing is drawn, look at `aircraft.max_shown`,
`hide_ground` and the altitude filters.

## The ADS-B rate will not go below 1 second

That is the provider's published limit, not a bug. See [ADS-B](ADS-B.md).

## Panel is cut off at the bottom

Panels do not scroll, and a panel taller than the terminal loses its bottom rows.
Fold a section, minimise with `[-]`, drag it up, or use a taller terminal.

## Snapshot did something unexpected

Check `snapshot.png_mode`. `map` re-renders the map and does not include labels
or aircraft unless you turn them on. `ascii` exports the terminal view, which
already has everything on it.

## Themes look wrong after an update

```
./configure.sh set ui.theme amber
```

Or delete the theme block in `config.json` to drop any colour overrides. Config
values are range checked on load, so a bad value falls back rather than breaking.
