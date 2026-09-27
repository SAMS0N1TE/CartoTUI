# Geometry, movable panels and visual QA

Build: 0.13.1.dev2.

## Controls

Press **Tab** or **W** to open the compact settings navigator. Its height follows
the current page, up to the available terminal height; long pages still scroll.
Choose **Movable windows**, or use **Open movable window** at the bottom of a
widget's settings page. Drag its title bar, collapse with `[-]`, close with `[x]`.
Positions and visibility are saved. Floating panels share the navigator's
readable theme styling. Keyboard navigation remains available in the navigator
when mouse reporting is unavailable over SSH.

Under **Map appearance → Geometry**:

* **standard**: the existing image-to-character map.
* **solid**: keep the selected map rendering and overlay roads and water outlines
  projected directly from vector tile coordinates as connected terminal glyphs.
* **vector-only**: draw geometry and labels on a plain theme background; add
  building outlines at street zooms. Skip image rasterisation and cellification.
  Image fills and weather radar are intentionally absent in this mode.

These are terminal geometry modes, not SVG or a terminal graphics extension.
Their resolution is limited by character cells. The two new modes are opt-in;
dense road networks can merge at low terminal resolutions. Thin geometry uses
theme-aware contrast and zoom gates. Source tile clipping edges are excluded
from polygon outlines. Geometry is clipped before walking cells, preventing
overzoomed segments from producing unbounded off-screen work.

**Street / POI labels** enables named streets, transit stops, water features and
POIs when provided by the vector source. Streets begin at z13, other details at
z14, subject to the provider's minimum zoom. City/region labels take priority,
and collision checking prevents overlapping text. Larger terminals can fit more
labels. Layer extents are normalized before projection.

The experimental braille contrast and sparse-texture pass introduced in dev1
was removed in dev2. It amplified background texture and introduced repetitive
horizontal patterns. Braille again preserves the renderer's original glyph masks
and colours, including when loading a saved dev1 configuration. The movable
panels, detail labels and opt-in geometry modes remain available.

## Repeatable visual review

From the repository, with its Python environment:

```powershell
python tools/qa_settings.py --out ../settings-review --cache ../../work/qa-tiles
```

Open `index.html` in the output directory. Filter by theme, zoom, glyph mode or
geometry mode, or check **Warnings only**. `--gallery-only --out PATH` rebuilds
the gallery instantly from existing results without rerendering. `results.json` records coverage, labels, timings, ink coverage,
foreground/background contrast and ANSI output sizes in both 256 and truecolour.
The normal matrix has 720 cases: 10 themes × 6 representative zooms × 4 glyph
modes × 3 geometry modes. Tiles are cached after the first download.

For every zoom:

```powershell
python tools/qa_settings.py --out ../all-zooms --cache ../../work/qa-tiles --themes paper,night --zooms 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19
```

For the full categorical palette/threshold/shading/colour product at a selected
location and zoom, add `--full`. This is 2,400 cases per theme/zoom with the
current palettes. Add `--dithers none,bayer,atkinson,floyd` to multiply by four;
dithering is relevant to ASCII. Use `--width`, `--height`, `--lat`, `--lon`,
`--themes`, `--zooms` and `--limit` to scope a run. Large full matrices can take
substantial time. Every case is measured; the gallery keeps representative
cases and warnings rather than an image of every redundant combination.

This is not an exhaustive proof of visual quality. Continuous tone controls,
every location, external radar data, terminal fonts and terminal colour settings
cannot be exhausted by a finite matrix. Low contrast and low tonal range are
review warnings, not automatic failures: open ocean or empty land can correctly
be sparse. Inspect the gallery as well as the metrics. The tests also exercise
keyboard interaction through a VT100 terminal; a remote SSH host was not used.

## Performance characteristics

Projection batches source segments into NumPy arrays, clips them to the visible
viewport, quantizes once, and removes duplicate terminal segments before
drawing. The prepared segment cache is bounded to 16 MiB and 256 layer entries;
four recent compiled projections are retained. Weak tile identity guards
against reusing geometry from another tile generation.

In one local 160×60 Boston z13 worker run, repeated frames took approximately
7.0 ms standard, 2.3 ms solid, and 0.9 ms vector-only. The first solid frame took
518 ms including tile decoding/preparation; the first vector-only frame after
that took 102 ms. These are measurements of one scene, not general FPS claims.
First visits to dense areas can still pause; the default remains standard mode.
