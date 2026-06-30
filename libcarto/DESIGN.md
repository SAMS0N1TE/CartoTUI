# libcarto — design contract

`libcarto` is a freestanding C99 vector-map renderer. It is the **single
source of truth** for drawing maps in CartoTUI. The desktop terminal app
and the ESP32-P4 firmware both consume it; nothing renders twice.

This document is the Phase-0 contract. It records the locked decisions,
the architecture, the public API surface, and the phased roadmap. Headers
under `include/carto/` are the machine-readable half of this contract.

---

## Why this exists

CartoTUI's current vector path cheats: `MVT → VectorTile → PIL bitmap →
luminance/threshold → glyphs`. The bitmap stage throws away geometry, then
tries to recover structure from pixels. The real renderer keeps geometry
*as geometry* until the last possible moment:

```
MVT → decode → project + clip to viewport (Q16.16) → draw primitives into
a subpixel framebuffer → pack framebuffer into cells / push to panel
```

That change simultaneously (1) replaces the screenshot hack with true
vector rendering, (2) produces a portable core that compiles for a
400 MHz RISC-V part — something mapscii (Node.js) structurally cannot do,
and (3) becomes the shared map layer for the LakeShark ADS-B handheld.

---

## Locked decisions (2026-06-30)

**D1 — Imagery path: Python-only.** `libcarto` is **vector-only** and
freestanding (no JPEG/PNG decoders, no libc surprises). The image→glyph
path is retained but scoped strictly to genuine raster imagery (satellite,
hillshade, OpenTopoMap) and lives in `cartotui/rendering/imagery.py`,
desktop-only. CartoTUI is therefore **dual-pipeline**: true-vector via the
C core for vector sources, image→glyph in Python for imagery. The device
never needs an image decoder.

**D2 — Tiles: validate on MVT, ship on baked `.carto`.** Desktop Phase 1
parses real PMTiles/MVT directly (one decoder to validate the rasterizer
against). The device path is the **pre-baked compact `.carto` format**
(int16 quantized coords, per-zoom simplified, layer-tagged, no protobuf
parser on the MCU) loaded from the **SD card**. `tools/tilebake.c` is a
committed deliverable, not optional. Rationale: on a constrained MCU the
baked format is decisively faster and smaller; on desktop, MVT avoids a
baking step during development.

**D3 — Display: color-first, mono as a first-class mode.** RGB565 color
LCD is the primary device target. `CARTO_FMT_MONO1` is a first-class
framebuffer mode for the Sharp LS027B7DH01 / e-ink. Consequence: the
palette / dither / truecolor aesthetic **carries onto the color device**,
not just the desktop terminal — strengthening the "real subpixel-aesthetic
engine on an MCU" differentiator.

---

## Architecture

```
            ┌──────────────────────── libcarto (C99) ───────────────────────┐
            │ arena · fixedpt · mvt_stream · geom · raster · labels · style  │
            │                      → framebuffer                             │
            └───────────────▲───────────────────────────────▲───────────────┘
                            │ cffi (API mode)                │ ESP-IDF component
            ┌───────────────┴──────────────┐   ┌─────────────┴───────────────┐
            │ Desktop: cartotui (Python)   │   │ Firmware: esp32p4           │
            │ prompt_toolkit shell, packer │   │ esp_lcd backend, SD tiles,  │
            │ palette/dither, imagery path,│   │ buttons, ADS-B layer from   │
            │ traffic/ADS-B, fetch/cache   │   │ LakeShark RTL-SDR pipeline  │
            └──────────────────────────────┘   └─────────────────────────────┘
```

The C core renders into a `carto_framebuffer`. It does not own the screen,
the network, the filesystem, or a terminal. Fetch/cache stays in Python on
desktop and becomes SD reads on device; both feed bytes to the same core.

### Data flow, vector path (replaces `raster_vector.rasterise_view`)

1. **fetch/cache** (Python `vector_source.py` / device SD) → raw tile bytes
2. **mvt_stream** → stream-decode protobuf, emit geometry directly into the
   arena/rasterizer. No dict-of-features materialization (this is also the
   fix for the PSRAM-fragmentation risk).
3. **geom** → project tile coords (extent 4096) to framebuffer space in
   Q16.16, clip to viewport.
4. **style** → resolve per-layer/class draw order, color, stroke width.
5. **raster** → thick polylines (Bresenham + brush stamp), polygon fill
   (scanline, even-odd / nonzero), point markers, into the framebuffer.
6. **labels** → collision resolution (grid-occupancy v1), stamp text. This
   is genuinely net-new; today labels are baked into the bitmap and would
   be lost going vector.
7. **consumer** → packer turns subpixel framebuffer into prompt_toolkit
   fragments (desktop) / `esp_lcd` pushes it to the panel (device).

---

## Module / API surface

Public headers live in `include/carto/`. One translation unit per module
in `src/`. Everything is `carto_`-prefixed, C99, no globals, no malloc on
the hot path (the arena owns all per-frame allocation).

| Module        | Header           | Responsibility |
|---------------|------------------|----------------|
| fixedpt       | `fixedpt.h`      | Q16.16 type + ops. Header-only. **Done (Phase 0).** |
| framebuffer   | `framebuffer.h`  | Output target, 4 pixel formats, subpixel/cell model. **Header done.** |
| arena         | `arena.h`        | Bump allocator over a caller-provided buffer (SRAM/PSRAM). Per-viewport reset. |
| style         | `style.h`        | Layer draw-order table, per-class color+width, palette. Ports `VectorStyle` + `ROAD_CLASS_PRIORITY`. *(awaiting extract)* |
| mvt_stream    | (internal)       | Streaming MVT/protobuf decoder → geometry callbacks. |
| geom          | (internal)       | project (tile→fb, Q16.16) + viewport clip (Sutherland–Hodgman). |
| raster        | (internal)       | line/polyline/scanline-fill/point primitives. |
| labels        | (internal)       | collision grid, text placement. |
| carto         | `carto.h`        | Public umbrella: context, viewport, `carto_render_tile()`. |

### Top-level call (provisional shape, finalized with `carto.h`)

```c
carto_ctx     ctx;     /* holds arena, style, scratch */
carto_viewport vp;     /* center lat/lon or tile xyz, zoom, fb dims */
carto_framebuffer fb;  /* caller-owned output */

carto_render_begin(&ctx, &fb, &vp, &style);
carto_render_tile(&ctx, tile_bytes, len, tile_x, tile_y, tile_z); /* per tile */
carto_render_overlay(&ctx, points, n);  /* ADS-B / dynamic layer */
carto_render_end(&ctx);  /* flush labels (collision needs all geometry first) */
```

Labels flush at `render_end` because collision resolution needs the full
frame's geometry before placing text.

---

## Fixed-point convention

Q16.16 (`carto_fix`, `fixedpt.h`). Integer part holds framebuffer + clip
coordinates; 16 fractional bits give sub-pixel positioning for crisp
strokes. Multiply/divide use a 64-bit intermediate. One float→fix setup
per viewport (the projection scale/offset); everything downstream is
integer. Deterministic and identical on x86-64 and RV32.

---

## Framebuffer & packer model

See `framebuffer.h` for the full table. Key points:

- The core fills a framebuffer at the consumer's resolution and format.
- **Braille** desktop: MONO1 coverage mask at `(cols*2 × rows*4)` + a
  per-cell RGB565 color plane at `(cols × rows)`. Crisp geometry, one
  color per cell. **Quadrant**: INDEXED8 at `(cols*2 × rows*2)`, two
  colors/cell via fg+bg. **ASCII**: luma→glyph.
- **Color LCD**: RGB565 at panel resolution, `cell_color = NULL`.
- **Sharp/e-ink**: MONO1 at panel resolution.
- The honest tradeoff (braille/mono): geometry is crisp, color is per-cell
  not per-subpixel. That's the deliberate trade for geometric sharpness —
  the whole point of going vector.

---

## Phased roadmap (reflecting locked decisions)

- **Phase 0 — API as headers + this contract.** `fixedpt.h`,
  `framebuffer.h` done; `arena.h`, `style.h`, `carto.h` next (style.h
  waits on the existing-definitions extract). *(in progress)*
- **Phase 1 — Build `libcarto` on Linux, standalone.** Modules: arena,
  fixedpt, mvt_stream, geom, raster, labels, style, framebuffer. Harness
  `tests/render_to_png.c` feeds a PMTiles tile + viewport and dumps PNG.
  **Golden-image diffs checked in from day one** so polyline joins /
  nonzero-fill can't silently regress. De-risks the rasterizer before any
  embedded pain.
- **Phase 2 — Bind into Python via cffi (API mode).** Rip out
  `raster_vector.rasterise_view` for vector sources; C core renders into a
  subpixel/indexed buffer, a thin `rendering/packer.py` makes
  prompt_toolkit fragments with the palette/dither/truecolor layer. The
  whole TUI shell stays (sidebar, compass, goto, themes, statusbar). The
  **recovered `_OLD` features land here**: airplane `marker_size`,
  favorites, profiles, name_prompt, pmtiles_download. Needs a C toolchain
  on the Windows dev box (MSVC/clang).
- **Phase 3 — ESP-IDF component.** `libcarto` compiles as-is. Add `esp_lcd`
  RGB565 backend (+ MONO1 path for Sharp), SD-card `.carto` tile loading,
  the `tilebake.c` desktop baker, button input.
- **Phase 4 — ADS-B overlay on device.** LakeShark aircraft lat/lon feed
  `libcarto` as a dynamic point/line layer drawn after the basemap. The
  demo that sells the project.

---

## Directory structure (target)

```
cartotui/
├── libcarto/                 # portable C99 core (THIS)
│   ├── include/carto/        # carto.h framebuffer.h style.h fixedpt.h arena.h
│   ├── src/                  # arena mvt_stream geom raster labels style framebuffer
│   ├── tools/tilebake.c      # desktop: PMTiles/MVT -> compact .carto
│   ├── tests/render_to_png.c # phase-1 visual + golden harness
│   └── CMakeLists.txt
├── bindings/python/          # _carto_build.py (cffi), carto_ffi.py
├── cartotui/                 # existing Python app, slimmed
│   ├── ui/                   # prompt_toolkit shell (kept)
│   ├── rendering/packer.py   # framebuffer -> braille/quadrant + palette/dither
│   ├── rendering/imagery.py  # kept image->glyph path, imagery-only
│   ├── vector_source.py      # kept for fetch/cache; decode moves to C
│   └── traffic/              # ADS-B (kept)
├── firmware/esp32p4/         # ESP-IDF: app_main, lcd (rgb565+sharp), tiles_sd
│   └── components/libcarto/  # -> ../../libcarto
└── tiles/                    # baked .carto tiles for the device
```

Phase 0 only **adds** `libcarto/`; it touches no existing file. The
`cartotui/` reshuffle happens in Phase 2.

---

## Open questions / risks (to resolve in Phase 1)

1. **`cell_color` coupling (framebuffer.h)** — carry per-cell color as a
   plane, or have the packer derive it by sampling the full-res buffer?
   Provisional: plane. Decide once the packer is real.
2. **Labels module** — grid-occupancy v1; defer the R-tree until it's a
   measured bottleneck. Highest-risk net-new module.
3. **Polygon fill rule** — nonzero vs even-odd per layer (buildings vs
   multipolygon water with holes). Golden tests must cover holes.
4. **Stroke joins/caps** — brush-stamp Bresenham is simplest; revisit if
   thick roads show gaps at sharp turns (stroke-to-polygon fallback).
5. **`.carto` format spec** — finalized in Phase 3 against measured P4
   memory/perf, not guessed now.
