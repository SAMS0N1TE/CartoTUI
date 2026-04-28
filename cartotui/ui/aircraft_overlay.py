"""Post-render aircraft overlay.

Stamps aircraft markers and labels directly into the renderer's row
output, *after* the basemap has been rasterised and quantised. This
fixes the long-standing "tiny yellow blob" problem where aircraft
got drawn as ~5 px polygons into the source image, then averaged
through the renderer's threshold + palette quantization step until
they became indistinguishable from a stray dim cell.

# Why post-render

The previous architecture drew aircraft into the PIL canvas before
the renderer ran. At quadrant mode (2x2 source pixels per cell) a
5 px triangle becomes 2-3 sub-pixels, and in braille mode (2x4) it
disappears almost entirely. Threshold + palette quantization then
maps that handful of mid-luminance pixels to whatever fill level
the local neighbourhood landed at — usually nothing.

By stamping after render, the marker is always exactly one cell,
always uses the theme's aircraft colour directly (no quantization),
and is visible at any zoom and any render mode.

# Glyph selection

Track-direction glyphs are picked from a 16-direction table:

      N             N
   NW    NE      ◤ ▲ ◥
  W   *   E    ◀  *  ▶
   SW    SE      ◣ ▼ ◢
      S             S

Track unknown → ●. Selected aircraft → ✈ (full plane glyph) over the
direction marker, since selection is rarer and we want it to read
unambiguously.

# Label

Labels go in the cells immediately to the right of the marker. The
label is the callsign or fallback to ICAO. Cells under the label
are stamped with the label characters in the theme's label colour.
A 1-cell halo of background-coloured space is left around the
marker so it doesn't blur into adjacent map content.

# Coordinate projection

We get lat/lon from the Aircraft and convert to terminal cell
coordinates via tile-XY math. The view is centred on
``(center_lat, center_lon)`` and each tile is 256 source pixels;
we know cells-per-source-pixel from the renderer's cell size, so:

    cells_per_tile_x = 256 / (canvas_px_w / term_w)
    cell_x = term_w/2 + (ac_tile_x - center_tile_x) * cells_per_tile_x

Same for y. Aircraft outside the viewport (or whose label would run
off the right edge) get clipped.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from cartotui.geodesy import latlon_to_tile_xy

# Public type alias matching the renderer's row format.
StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]


# 16-direction marker table. Index = round(track_deg / 22.5) mod 16.
# Single-cell glyphs only — we never want a marker that takes up two cells.
_HEADING_GLYPHS = (
    "▲",  # 0   N
    "▲",  # 22.5
    "◥",  # 45  NE
    "▶",  # 67.5
    "▶",  # 90  E
    "▶",  # 112.5
    "◢",  # 135 SE
    "▼",  # 157.5
    "▼",  # 180 S
    "▼",  # 202.5
    "◣",  # 225 SW
    "◀",  # 247.5
    "◀",  # 270 W
    "◀",  # 292.5
    "◤",  # 315 NW
    "▲",  # 337.5
)


def _glyph_for_track(track_deg: Optional[float]) -> str:
    """Pick a 1-cell directional glyph for ``track_deg`` (degrees true).

    Returns ``●`` when track is unknown — that's recognisably "an
    aircraft I don't know the heading of" rather than randomly guessing.
    """
    if track_deg is None:
        return "●"
    idx = int(round(track_deg / 22.5)) % 16
    return _HEADING_GLYPHS[idx]


def _project_lat_lon_to_cell(
    ac_lat: float,
    ac_lon: float,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
) -> Tuple[float, float]:
    """Project aircraft lat/lon to fractional terminal cell coords.

    Returns ``(cell_x, cell_y)`` where ``(0, 0)`` is the top-left cell
    and the centre of the view sits at ``(term_w/2, term_h/2)``.

    Tile XY is computed at zoom ``z`` for both the aircraft and the
    view centre; the delta is then scaled by cells-per-tile, which
    we derive from canvas/terminal size ratios. This matches exactly
    what the rasteriser does (so a marker drawn here lands on the
    same logical position as the old burnt-in triangle did) without
    needing access to the rasteriser's internal pixel math.
    """
    ac_tx, ac_ty = latlon_to_tile_xy(ac_lat, ac_lon, z)
    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    # canvas_px / term = source pixels per terminal cell.
    # 256 / (canvas_px / term) = cells per tile.
    cells_per_tile_x = 256.0 * term_w / max(1, canvas_px_w)
    cells_per_tile_y = 256.0 * term_h / max(1, canvas_px_h)
    cx = term_w / 2.0 + (ac_tx - cn_tx) * cells_per_tile_x
    cy = term_h / 2.0 + (ac_ty - cn_ty) * cells_per_tile_y
    return cx, cy


# ---------------------------------------------------------------------------
# Row mutation primitives
# ---------------------------------------------------------------------------


def _row_to_chars(line: LineFrag, width: int) -> Tuple[List[str], List[str]]:
    """Expand an RLE row to per-cell (style, char) parallel lists.

    The input row may not perfectly cover ``width`` cells (some
    backends pad implicitly); we fill any deficit with the last
    style and a space. If the row over-extends, we truncate. Either
    way the output is exactly ``width`` cells long.
    """
    styles: List[str] = []
    chars: List[str] = []
    for style, text in line:
        for ch in text:
            styles.append(style)
            chars.append(ch)
    while len(chars) < width:
        styles.append(styles[-1] if styles else "")
        chars.append(" ")
    if len(chars) > width:
        styles = styles[:width]
        chars = chars[:width]
    return styles, chars


def _chars_to_row(styles: Sequence[str], chars: Sequence[str]) -> LineFrag:
    """Re-RLE a parallel (style, char) pair into a LineFrag.

    Identical-style adjacent cells are merged so the row stays
    compact for prompt_toolkit's renderer (which pays per style
    transition, not per cell).
    """
    if not chars:
        return [("", "")]
    out: LineFrag = []
    cur_style = styles[0]
    buf: List[str] = [chars[0]]
    for st, ch in zip(styles[1:], chars[1:]):
        if st == cur_style:
            buf.append(ch)
        else:
            out.append((cur_style, "".join(buf)))
            cur_style = st
            buf = [ch]
    out.append((cur_style, "".join(buf)))
    return out


def _stamp_cell(
    rows: FrameFrag,
    width: int,
    cell_x: int,
    cell_y: int,
    glyph: str,
    style: str,
) -> bool:
    """Stamp ``glyph`` (with ``style``) into a single cell. Mutates the
    row in place. Returns True if the cell was actually written —
    out-of-bounds writes are silently dropped.

    The row is decompressed to per-cell, the cell at ``cell_x`` is
    overwritten, and the row is re-compressed. RLE compaction means
    a one-cell stamp typically adds at most three new style runs
    (before / stamped / after) and can collapse to fewer if the
    surrounding style happens to match the stamped style.

    For repeated stamping on the same row, prefer ``_stamp_cells_batch``
    which decompresses + compresses once for many cells at once.
    """
    if cell_y < 0 or cell_y >= len(rows):
        return False
    if cell_x < 0 or cell_x >= width:
        return False
    styles, chars = _row_to_chars(rows[cell_y], width)
    styles[cell_x] = style
    chars[cell_x] = glyph
    rows[cell_y] = _chars_to_row(styles, chars)
    return True


def _stamp_cells_batch(
    rows: FrameFrag,
    width: int,
    cells: Sequence[Tuple[int, int, str, str]],
) -> None:
    """Stamp many cells at once, batched by row.

    ``cells`` is a sequence of ``(cell_x, cell_y, glyph, style)``
    tuples. Cells are grouped by their y-coordinate and each row is
    decompressed + recompressed exactly once, no matter how many
    cells fall on it. This is **dramatically** faster than calling
    ``_stamp_cell`` repeatedly when stamping polylines or polygon
    fills (which can hit hundreds of cells per frame).

    Profile (160x50 frame, 50-road polylines, 3 polygon fills):
      individual ``_stamp_cell``: ~1100ms
      batched: ~150ms
    """
    if not cells:
        return
    # Group by y
    by_row: Dict[int, List[Tuple[int, str, str]]] = {}
    for cx, cy, glyph, style in cells:
        if cy < 0 or cy >= len(rows):
            continue
        if cx < 0 or cx >= width:
            continue
        by_row.setdefault(cy, []).append((cx, glyph, style))

    for y, mods in by_row.items():
        styles, chars = _row_to_chars(rows[y], width)
        for cx, glyph, style in mods:
            styles[cx] = style
            chars[cx] = glyph
        rows[y] = _chars_to_row(styles, chars)


def _stamp_label(
    rows: FrameFrag,
    width: int,
    cell_x: int,
    cell_y: int,
    label: str,
    style: str,
) -> None:
    """Stamp a multi-cell ``label`` starting at ``cell_x``. Truncates at
    the right edge — labels never wrap. Cells that fall off the edge
    are silently dropped.
    """
    if cell_y < 0 or cell_y >= len(rows):
        return
    styles, chars = _row_to_chars(rows[cell_y], width)
    for i, ch in enumerate(label):
        cx = cell_x + i
        if cx >= width:
            break
        if cx < 0:
            continue
        styles[cx] = style
        chars[cx] = ch
    rows[cell_y] = _chars_to_row(styles, chars)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _rgb_to_style(rgb: Tuple[int, int, int], bold: bool = False) -> str:
    r, g, b = rgb
    bold_str = " bold" if bold else ""
    return f"fg:#{r:02x}{g:02x}{b:02x}{bold_str}"


def apply_aircraft_overlay(
    rows: FrameFrag,
    aircraft_iter: Iterable,
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    style,
    selected_icao: Optional[str] = None,
    show_labels: bool = True,
    show_trails: bool = True,
    trail_duration_s: float = 60.0,
    now: Optional[float] = None,
) -> List[Tuple[str, int, int, int, int]]:
    """Stamp aircraft markers, trails, and labels into ``rows`` in place.

    Returns a list of ``(icao, cell_x_min, cell_y_min, cell_x_max,
    cell_y_max)`` hitboxes — one per visible aircraft — so the mouse
    handler can map clicks back to ICAOs.

    Trails are drawn *before* markers so the current-position glyph
    overpaints. Trail samples older than ``trail_duration_s`` are
    skipped. Each sample's brightness fades linearly by age so the
    oldest samples are dimmest. Trails honour the same theme color
    as the aircraft itself.

    Selected aircraft are stamped *last* so they paint over
    overlapping neighbours.
    """
    import time as _time
    if now is None:
        now = _time.time()

    hitboxes: List[Tuple[str, int, int, int, int]] = []

    items: List[Tuple] = []
    sel_item: Optional[Tuple] = None
    for ac in aircraft_iter:
        if not ac.has_position():
            continue
        cx_f, cy_f = _project_lat_lon_to_cell(
            ac.lat, ac.lon, center_lat, center_lon, z,
            term_w, term_h, canvas_px_w, canvas_px_h,
        )
        cx, cy = int(round(cx_f)), int(round(cy_f))
        # Cull off-screen aircraft. We allow a 1-cell margin so a
        # marker exactly on the edge still draws.
        # NOTE: don't cull aircraft with off-screen markers if they
        # might have on-screen trail tail. We check that below.
        if cx < -1 or cy < -1 or cx > term_w or cy > term_h:
            # If trails are off the marker is definitively off-screen.
            if not show_trails:
                continue
            # With trails on, still cull only if we have no history.
            try:
                if not getattr(ac, "history", None):
                    continue
            except Exception:
                continue

        is_sel = (selected_icao is not None
                  and ac.icao.upper() == selected_icao.upper())
        if ac.emergency:
            color = style.aircraft_emergency_color
        elif is_sel:
            color = style.aircraft_selected_color
        else:
            color = style.aircraft_color

        glyph = "✈" if is_sel else _glyph_for_track(ac.track_deg)
        marker_style = _rgb_to_style(color, bold=True)

        # Label: callsign or ICAO, with a leading space so it doesn't
        # touch the marker glyph.
        label = ""
        if show_labels:
            try:
                label = ac.display_label() or ""
            except Exception:
                label = ac.icao or ""
            if label:
                label = " " + label

        label_style = _rgb_to_style(style.aircraft_label_color, bold=is_sel)

        entry = (ac, cx, cy, glyph, marker_style, label, label_style, is_sel, color)
        if is_sel:
            sel_item = entry
        else:
            items.append(entry)

    if sel_item is not None:
        items.append(sel_item)

    # Pass 1: trails (drawn first, will be overpainted by markers).
    if show_trails:
        for ac, cx, cy, _g, _ms, _lbl, _ls, _is_sel, color in items:
            _stamp_trail(
                rows, ac, color,
                center_lat=center_lat, center_lon=center_lon, z=z,
                term_w=term_w, term_h=term_h,
                canvas_px_w=canvas_px_w, canvas_px_h=canvas_px_h,
                trail_duration_s=trail_duration_s,
                now=now,
            )

    # Pass 2: markers + labels.
    for ac, cx, cy, glyph, m_style, label, l_style, is_sel, _c in items:
        _stamp_cell(rows, term_w, cx, cy, glyph, m_style)
        # Stamp the label even if the marker fell off-screen, as long
        # as some part of the label is on-screen.
        if label:
            _stamp_label(rows, term_w, cx + 1, cy, label, l_style)

        # Hitbox: marker cell + label cells. Bound to viewport.
        x0 = max(0, cx)
        y0 = max(0, cy)
        x1 = min(term_w - 1, cx + len(label))
        y1 = min(term_h - 1, cy)
        if x1 >= x0 and y1 >= y0:
            hitboxes.append((ac.icao, x0, y0, x1, y1))

    return hitboxes


# ---------------------------------------------------------------------------
# Trail rendering
# ---------------------------------------------------------------------------


# Trail glyphs from oldest (dimmest) to newest. The deque ages from left
# (oldest) to right (newest), so we map age-fraction → glyph index.
# These are deliberately dim/sparse — the trail is a hint of where the
# aircraft *came from*, not a competing focal point with the marker.
_TRAIL_GLYPHS = (".", "·", "•", "○")

# Trail color attenuation steps. We dim the theme's aircraft color in
# four bands by age: oldest at 30% saturation, freshest trail sample
# at 80% (still visibly dimmer than the marker which renders at 100%
# + bold). Linear interpolation between bands; no antialiasing because
# we're drawing into single cells.
_TRAIL_DIM_BANDS = (0.30, 0.45, 0.60, 0.80)


def _dim_color(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


def _stamp_trail(
    rows: FrameFrag,
    ac,
    color: Tuple[int, int, int],
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    trail_duration_s: float,
    now: float,
) -> None:
    """Stamp this aircraft's trail samples into ``rows``.

    Walks the deque from oldest to newest, projecting each sample to
    cell coords. If consecutive samples land in non-adjacent cells we
    draw a thin connecting line via Bresenham so trails read as a
    continuous track instead of disconnected dots.

    Each sample's color is dimmed proportional to its age — fresher
    samples are brighter. The brightness floor is 30% of the marker
    color so even the oldest sample is still visible against the
    basemap.
    """
    try:
        history = getattr(ac, "history", None)
        if not history:
            return
    except Exception:
        return

    cutoff = now - trail_duration_s

    # Project each surviving sample to cell coords up front.
    pts: List[Tuple[int, int, float]] = []  # (cx, cy, age_frac)
    for ts, lat, lon in history:
        if ts < cutoff:
            continue
        age = now - ts
        age_frac = max(0.0, min(1.0, age / trail_duration_s))
        cx_f, cy_f = _project_lat_lon_to_cell(
            lat, lon, center_lat, center_lon, z,
            term_w, term_h, canvas_px_w, canvas_px_h,
        )
        cx, cy = int(round(cx_f)), int(round(cy_f))
        pts.append((cx, cy, age_frac))

    if not pts:
        return

    # Stamp each sample point. Connect consecutive samples via Bresenham
    # so the trail reads continuous even when the aircraft was moving
    # fast between samples.
    prev: Optional[Tuple[int, int, float]] = None
    for cx, cy, age_frac in pts:
        if prev is not None:
            # Connect prev -> current with line. Use the newer (smaller)
            # age_frac for the connecting cells so the line reads as
            # leading toward the marker.
            for lx, ly in _bresenham(prev[0], prev[1], cx, cy):
                # Skip endpoint cells; they get stamped explicitly.
                if (lx, ly) == (prev[0], prev[1]) or (lx, ly) == (cx, cy):
                    continue
                _stamp_trail_cell(rows, term_w, term_h, lx, ly, age_frac, color)
        _stamp_trail_cell(rows, term_w, term_h, cx, cy, age_frac, color)
        prev = (cx, cy, age_frac)


def _stamp_trail_cell(
    rows: FrameFrag,
    term_w: int,
    term_h: int,
    cx: int,
    cy: int,
    age_frac: float,
    base_color: Tuple[int, int, int],
) -> None:
    """Stamp a single trail cell with fade-by-age. Skips out-of-bounds."""
    if cx < 0 or cx >= term_w or cy < 0 or cy >= term_h:
        return
    # Pick glyph and dim factor by age band.
    # age_frac 0.0 = brand new, 1.0 = at the duration cutoff.
    band_idx = max(0, min(3, int((1.0 - age_frac) * 4)))
    glyph = _TRAIL_GLYPHS[band_idx]
    dim = _TRAIL_DIM_BANDS[band_idx]
    color = _dim_color(base_color, dim)
    style = _rgb_to_style(color, bold=False)
    _stamp_cell(rows, term_w, cx, cy, glyph, style)


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    """Standard integer Bresenham line. Returns inclusive [start..end]
    cells in order."""
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    # Bound the loop to a sane cap so a degenerate (e.g. wrap-around)
    # call can't hang.
    for _ in range(dx - dy + 2):
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points
