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


## Architecture


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

