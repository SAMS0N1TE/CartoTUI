# cartotui ↔ libcarto binding

`ctypes` binding that lets the Python app call the C renderer. No cffi /
MSVC toolchain needed — libcarto is built as a shared library with clang
and loaded directly.

## Build the shared library

```
cd libcarto
clang -shared -O2 -Iinclude \
  src/style.c src/framebuffer.c src/raster.c src/geom.c src/mvt.c src/carto.c \
  -o build/carto.dll -lm -static-libgcc
```

(`-static-libgcc` makes the DLL self-contained so ctypes loads it without
extra runtime DLLs on PATH. On Linux/macOS output `libcarto.so` / `.dylib`.)

## Modules

- `carto_ffi.py` — `Renderer.render_tile(tile_bytes, z, x, y, w, h) -> rgb565`
  loads the DLL, sets up the arena/framebuffer/viewport, calls
  `carto_begin`/`carto_render_tile`/`carto_end`, returns the RGB565 buffer.
- `packer.py` — framebuffer → terminal:
  - `to_ansi_halfblock(rgb565, w, h, cols, rows)` — truecolor `▀` cells
  - `to_bmp(...)` — debug image dump
