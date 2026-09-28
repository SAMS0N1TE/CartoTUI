# Native rendering pipeline

The map can remain in packed glyph/foreground/background arrays from libcarto
through overlay composition and terminal encoding. Python fragments are generated
lazily for exports, unsupported terminal depths, and compatibility rendering.
The settings/input UI continues to use prompt_toolkit.

## Quality and fallback rules

- Keep configured raster scale, colors, road widths, tone mapping, and sampling.
- Native luminance/blending kernels reproduce separate NumPy rounding operations;
  do not compile terminal.c with fast-math or contracted floating-point operations.
- Native ANSI encoding supports 256-color and truecolor. Other depths use the
  existing fragment encoder. Libraries missing new symbols also fall back.
- Every map cell is assumed to occupy one terminal column, as in the existing map
  renderer. The native interface is declared in `libcarto/include/carto/terminal.h`.
- Changes to visibility, origin, dimensions, or terminal colors invalidate previous
  cells. Dense updates choose the smaller full-frame or changed-cell stream.
- Braille preserves v0.13.0 glyph selection: flat regions use the selected
  palette (including `dos5`) and inherit the terminal background. Shading also
  substitutes palette glyphs in high-coverage cells. Adaptive is the default;
  stable is an optional alternate tone mapping. Packed output preserves these
  glyphs and colours rather than changing the rendering algorithm.

## Retained data

Each vector source owns a 32 MiB overlay cache of selectively decoded layers.
The full decoder remains available for the Python geographic renderer. Raw native
tiles include source identity in their keys and have a 64 MiB budget. Missing raw
tiles are retried rather than permanently cached as missing.

The native backend retains one complete viewport, keyed by source, geometry,
style/tone options, and raw-tile generation. The cell renderer retains one base
cell frame, returning copies before labels/aircraft modify it. Published frames
must not subsequently be mutated by the worker.

Projected label/boundary stamps retain their order, with compiled final foreground,
glyph, and explicit-background writes. Failed tile loads prevent retention of
incomplete overlay plans. Labels are tied to tile identity across source changes.

Radar tiles have a 64 MiB budget. A complete/partial composite can be reused until
its tile generation, weather frame, viewport, or options change. A retained radar
image is immutable to callers. Its identity participates in the cell cache key;
new weather data cannot reuse old cells.

## SSH and scheduling

`render.direct_paint` defaults on for VT-capable outputs. The regular renderer
remains available for legacy outputs and explicit opt-out. No GPU or terminal
image protocol is required.

Output write time feeds back into the map worker, whose request queue coalesces
camera changes. `render.output_mbps` optionally budgets uncompressed map bytes;
zero uses observed output backpressure. Settings → Performance exposes this as
**Link budget**, alongside encoding time and last output size. The budget changes
refresh cadence, never image quality. It is not automatic measurement of remote
network throughput, and terminal/SSH buffers can hide congestion.

## Validation

Run `python -m pytest`. The regression suite checks native/fragment cell equality,
truecolor and 256-color encoding, occlusion, sparse changes, cache invalidation,
decoder bounds, unshaded braille, native rounding, and VT100 keyboard sessions.

`tools/experiments/validate_integration.py --cache PATH --out PATH` exercises real
tiles, all zooms 0–19 in half/braille, two themes, and retained/fresh cell timings.
These are CPU measurements, not SSH or terminal presentation latency. Rebuild
libcarto with CMake before running native tests.

Hand-written assembly, host-specific ISA requirements, GPU-only rendering, and
direct semantic vector-to-cell rendering are not enabled. The tested AVX2 lookup
lost to scalar C; semantic rendering still needs separate visual-quality evidence.
