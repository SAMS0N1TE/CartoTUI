# ADS-B

CartoTUI can draw live aircraft on the map. It only reads ADS-B. Something else
has to decode 1090MHz and hand it over.

## Pick a source

```
./configure.sh adsb           # wizard, probes what you pick
./configure.sh adsb --source api
```

| Source | What it is |
| --- | --- |
| `api` | Free public feed over the internet. No hardware |
| `sbs1` | dump1090, readsb or PiAware on TCP 30003 |
| `lakeshark` | LakeShark receiver on USB serial |
| `lakeshark_tui` | LakeShark receiver, ESP_LOG console format |
| `replay` | Play back a recorded `.jsonl` |
| `disabled` | Off |

Non-interactive:

```
./configure.sh adsb --source sbs1 --host 192.168.1.50 --port 30003
./configure.sh adsb --source api --provider adsb.lol --radius 150
./configure.sh adsb --test
./configure.sh adsb --list-ports
./configure.sh adsb --disable
```

`--test` exits non-zero when the feed is unreachable, so it works in a health
check. Setting up a receiver server is covered in the README.

## Update rate

The ADS-B widget has an Update row, 0.5 to 10 seconds in half second steps. It
applies to the running source straight away, no restart.

The three API providers all publish a limit of about one request per second, and
CartoTUI holds you to it. Ask for 0.5s on a public provider and it settles at
1.0s, and the widget says so rather than showing you a rate you are not getting.
Going faster than a provider's published limit earns HTTP 429s, not fresher data.

| Provider | Floor |
| --- | --- |
| `airplanes.live` (default) | 1.0s |
| `adsb.lol` | 1.0s |
| `adsb.fi` | 1.0s |

A local receiver on `sbs1` is a stream, not a poll. Messages arrive as they
arrive, which is faster than any interval, so the widget shows "streaming" there
instead of a knob that would do nothing.

Radius is on the widget too, 25 to 250 nm, and also applies live.

## Display

The ADS-B widget's Display section, folded by default.

| Setting | Options |
| --- | --- |
| Labels | smart, all, selected, none |
| Markers | arrow, dot, large, plane, square |
| Size | small, normal, large, huge |
| Alt colours | Colour by altitude band |
| Legend | The altitude key |
| Trails | On or off, plus length from 5 to 600 seconds |
| Predicted | Projected track for the selected aircraft |
| Motion (DR) | Dead reckoning between updates |
| Highlight | Flag emergencies and other interesting traffic |

### Marker size

A terminal cell is a fixed size, so past a filled glyph the only way to draw a
bigger aircraft is to use more cells. `large` and `huge` grow wings either side
of the heading glyph, one cell out and two cells out. The wings are drawn across
the heading so the shape still points somewhere.

```
heading:     N       NE       E       SE
small        ▵        ◹        ▹        ◺
normal       ▲        ◥        ▶        ◢
large       ─▲─      ╲◥╲      │▶│      ╱◢╱
huge       ──▲──    ╲╲◥╲╲    ││▶││    ╱╱◢╱╱
```

Clicking a wing selects the aircraft, same as clicking the middle.

## Declutter

`max_shown` caps how many are drawn, nearest first. The selected aircraft is
always kept. `hide_ground` drops ground traffic. `min_altitude` and
`max_altitude` filter by band, and 0 means no limit.

## Selecting

Click an aircraft on the map, or a row in the widget's Nearest list. The widget
then shows type, operator, registration, altitude, speed, range and bearing, and
a silhouette for its category. `f` follows it, and the widget has Follow + zoom
and Center here.
