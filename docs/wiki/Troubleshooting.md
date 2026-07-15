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

## Black patches, especially over water

Fixed. Radar used to be composited into the map image before the renderer chose
its fill levels, so precipitation set the white point and crushed the map around
it. If you see this on an older build, turn the radar off to confirm, then
update.

## Brightness blows the map out to white

Use the white point instead. Brightness multiplies, so on a light theme it hits
white almost immediately, and white cannot hold colour. [Image
adjust](Image-adjust.md) has the detail.

## It crashed with no traceback

If the process died and the log has nothing, it was probably a native crash in
`libcarto`. On Linux with systemd:

```
coredumpctl list --since "-1 hour"
coredumpctl info <pid>
```

A stack ending in `carto_put_px` or another `carto_*` frame confirms it. Work
around it by switching the renderer:

```
./configure.sh set render.vector_engine python
```

One of these has been fixed: concurrent renders used to share one scratch arena,
so a PNG export running while the map was still drawing could corrupt the other's
framebuffer. Renders are serialised now.

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
