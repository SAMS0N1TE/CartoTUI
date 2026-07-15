# CartoTUI

Interactive map viewer for the terminal with vector or raster tiles rendered as
ASCII, Unicode quadrants, or braille.

## Setup

Windows (PowerShell):

    .\setup.ps1

macOS / Linux:

    ./setup.sh

This makes a `venv`, installs CartoTUI, and builds the native renderer if a C
compiler is present (otherwise the Python renderer is used). It then offers to
set up the ADS-B connection; skip that step with `-SkipAdsb` (or `--skip-adsb`).
Then run:

    python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2081 --lon -71.5376 --zoom 14

## ADS-B live traffic

CartoTUI can overlay live aircraft on the map. Pick and test a source:

    .\configure.ps1 adsb      # Windows
    ./configure.sh adsb

### No hardware

The quickest path — a free public feed, no receiver required:

    ./configure.sh adsb --source api

It follows the map centre as you pan. Providers: `airplanes.live` (default),
`adsb.lol`, `adsb.fi`.

### Your own receiver

| Source | What it is |
| --- | --- |
| `api` | Free public feed over the internet. No hardware |
| `sbs1` | dump1090 / readsb / PiAware, local or on the network (SBS-1, TCP 30003) |
| `lakeshark` | LakeShark receiver on a USB serial port |
| `lakeshark_tui` | LakeShark receiver, ESP_LOG console format |
| `replay` | Play back a recorded `.jsonl` capture |

The wizard probes whatever you pick, so you know it works before launching the
TUI. It can also be driven non-interactively:

    ./configure.sh adsb --source sbs1 --host 192.168.1.50 --port 30003
    ./configure.sh adsb --source api --provider adsb.lol --radius 150
    ./configure.sh adsb --test          # re-probe the saved source
    ./configure.sh adsb --list-ports    # show serial ports
    ./configure.sh adsb --disable

`--test` exits non-zero when the feed is unreachable, so it works in a health check.

### Setting up a receiver server

CartoTUI only reads ADS-B — something has to decode 1090MHz off an SDR and serve
it. To see what this machine has, and what it could install:

    ./configure.sh adsb --server-status
    ./configure.sh adsb --install-server              # shows the plan only
    ./configure.sh adsb --install-server --yes        # actually runs it

Backends are probed at runtime (`apt-cache policy`) rather than assumed, because
availability varies:

| Host | Backend |
| --- | --- |
| Raspberry Pi (ARM Debian: bullseye/bookworm/trixie) | `dump1090-fa` from the FlightAware repo. Serves SBS on 30003 out of the box |
| Debian/Ubuntu amd64 | `dump1090-mutability`, where the distro still ships it |
| Anything else Linux | `readsb` via the wiedehopf install script |
| Windows | Guided only — see below |

FlightAware builds `dump1090-fa` for **armhf/arm64 Debian only**, so it is not
offered on amd64 or Ubuntu, where apt could not resolve it.

`--install-server` prints the exact commands and does nothing without `--yes`.
The `readsb` route runs a third-party script as root and is never automated —
the plan pipes it through `less` so you read it first.

On **Windows** there is no packaged ADS-B server, and the SDR's driver must be
replaced with WinUSB via [Zadig](https://zadig.akeo.ie/) — an admin GUI step no
script can safely drive. `--install-server` prints the steps instead. Once
`dump1090.exe --net --net-sbs-port 30003` is running, point CartoTUI at it:

    .\configure.ps1 adsb --source sbs1 --host localhost --port 30003

## Settings

Edit `config.json` without hunting for the file:

    .\configure.ps1 set ui.theme dark      # Windows
    ./configure.sh set render.vector_scale 8
    ./configure.sh list --flat
    ./configure.sh themes

## Documentation

Full documentation is in [`docs/wiki`](docs/wiki/Home.md).

| | |
| --- | --- |
| [Installation](docs/wiki/Installation.md) | Setup, the native renderer, where files live |
| [Keybindings](docs/wiki/Keybindings.md) | Every key |
| [Rendering](docs/wiki/Rendering.md) | View modes, palettes, dither, thresholds, Looks |
| [Image adjust](docs/wiki/Image-adjust.md) | Brightness, contrast, gamma, saturation, levels |
| [Themes](docs/wiki/Themes.md) | Built-in themes and writing your own |
| [Configuration](docs/wiki/Configuration.md) | Everything in config.json |
| [ADS-B](docs/wiki/ADS-B.md) | Live aircraft, sources, receivers |
| [Overlays](docs/wiki/Overlays.md) | Weather radar |
| [Widgets](docs/wiki/Widgets.md) | The floating panels |
| [Snapshots](docs/wiki/Snapshots.md) | PNG and HTML export |
| [Troubleshooting](docs/wiki/Troubleshooting.md) | When something is wrong |
| [Architecture](docs/wiki/Architecture.md) | How the code fits together |
<img width="778" height="504" alt="Recording 2026-07-13 161020 (2)" src="https://github.com/user-attachments/assets/9634c44e-5cf8-4125-b013-ff643ab7ab36" />
<img width="1038" height="890" alt="weather2" src="https://github.com/user-attachments/assets/7af3b9a7-a692-4b2a-a4e8-1858495c5d36" />
<img width="1080" height="886" alt="Screenshot 2026-07-13 110100" src="https://github.com/user-attachments/assets/072d04d6-4983-4bde-a054-6bdc261575ec" />

---
[License](LICENSE)
