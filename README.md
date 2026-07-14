# CartoTUI

Interactive map viewer for the terminal with vector or raster tiles rendered as
ASCII, Unicode quadrants, or braille.

## Setup

Windows (PowerShell):

    .\setup.ps1

macOS / Linux:

    ./setup.sh

This makes a `venv`, installs CartoTUI, and builds the native renderer if a C
compiler is present (otherwise the Python renderer is used). Then run:

    python -m cartotui --mvt-url "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}" --lat 43.2081 --lon -71.5376 --zoom 14

## Settings

Edit `config.json` without hunting for the file:

    .\configure.ps1 set ui.theme dark      # Windows
    ./configure.sh set render.vector_scale 8
    ./configure.sh list --flat
    ./configure.sh themes

## Documentation

Full documentation is in the [wiki](https://github.com/SAMS0N1TE/CartoTUI/wiki).
<img width="778" height="504" alt="Recording 2026-07-13 161020 (2)" src="https://github.com/user-attachments/assets/9634c44e-5cf8-4125-b013-ff643ab7ab36" />
<img width="1038" height="890" alt="weather2" src="https://github.com/user-attachments/assets/7af3b9a7-a692-4b2a-a4e8-1858495c5d36" />
<img width="1080" height="886" alt="Screenshot 2026-07-13 110100" src="https://github.com/user-attachments/assets/072d04d6-4983-4bde-a054-6bdc261575ec" />

---
[License](LICENSE)
