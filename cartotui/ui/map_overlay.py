"""Place-label overlay for the vector map.

Stamps city/town/place names directly into the row data as character-
mode text after the basemap has rendered. This is the *only* thing
this module does — water, parks, roads, and the rest of the basemap
geometry stay rasterized through the PIL pipeline (which is what
they're good at). Labels need cell-mode treatment because at terminal
resolution, text drawn into PIL and then run through the threshold
+ palette quantization step becomes unreadable noise.

# Why labels-only

An earlier version of this module also stamped roads and water as
cell-mode geometry. That was a mistake: terminal cells make a poor
substitute for proper vector lines (a curving road through 50 cells
becomes a fence of `─` characters), and stamping water/parks
duplicated work the rasterizer was already doing well.

What the rasterizer *can't* do well is text. Even with a 6x11 default
font drawn into a high-res canvas, by the time the renderer downsamples
to terminal cells (2x2 in quadrant, 2x4 in braille) and applies
threshold quantization, the letters become indistinguishable scatter.
Cell-stamping skips all that — the text lives at the cell level from
the start, gets the theme's label color directly, no quantization.

# Layer support

Reads from MVT layers named in `_PLACE_LAYERS`. Recognizes Protomaps,
OpenMapTiles, and similar conventions. Properties looked up:

  * ``name:latin`` / ``name`` / ``name:en`` — display text
  * ``class`` / ``kind`` / ``pmap:kind`` — feature class for ranking
  * ``pmap:rank`` — Protomaps explicit rank if present

Ranks (lower = bigger):
  0 country, 1 state, 2 city, 3 town, 4 village, 5 suburb,
  6 neighbourhood, 7 locality, 8 hamlet, 9 unranked

The overlay sorts by rank ascending, places labels in that order,
and skips anything that would collide with an already-placed label
(1-cell margin). Caps at 32 labels per frame so we never bury the map.

# Coordinate projection

Identical to the aircraft overlay's: a tile's local pixel coords get
projected to view-cell coords through the rasterizer's canvas size
ratio. So a label-projected position lands exactly where the
rasterizer would have drawn the same point.

# Tile classification cache

Per-tile feature extraction is LRU-cached by ``(tile_z, tile_x,
tile_y)``. Decoded tiles don't change once loaded, only the projection
into the current view does. Cache holds the most recent 64 tiles —
typical viewport is 4-12 tiles so this is plenty.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Tuple

from cartotui.geodesy import latlon_to_tile_xy
from cartotui.ui.aircraft_overlay import (
    _chars_to_row,
    _row_to_chars,
    _stamp_label,
)

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]


# Layer name conventions (match raster_vector.py).
_PLACE_LAYERS = {"places"}


def _project_lat_lon_to_cell(
    lat: float,
    lon: float,
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
) -> Tuple[float, float]:
    """Project lat/lon to fractional cell coords. Same math as the
    aircraft overlay; duplicated here so this module doesn't need to
    reach into a private helper of another module."""
    ac_tx, ac_ty = latlon_to_tile_xy(lat, lon, z)
    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    cells_per_tile_x = 256.0 * term_w / max(1, canvas_px_w)
    cells_per_tile_y = 256.0 * term_h / max(1, canvas_px_h)
    cx = term_w / 2.0 + (ac_tx - cn_tx) * cells_per_tile_x
    cy = term_h / 2.0 + (ac_ty - cn_ty) * cells_per_tile_y
    return cx, cy


# ---------------------------------------------------------------------------
# Per-tile label extraction (cached)
# ---------------------------------------------------------------------------
#
# Each label candidate is (rank, min_zoom, name, tile_local_xy). The
# min_zoom field is derived from Protomaps-style ``pmap:min_zoom``
# property when present, or from a fallback table keyed on rank when
# absent. We use min_zoom for the visibility filter at render time:
# at view zoom ``z``, only labels with ``min_zoom <= z`` get
# stamped. This matches what the cartographer intended — Protomaps'
# min_zoom values are tuned by hand to keep label density readable
# at every zoom level.

_TILE_LABEL_CACHE: "OrderedDict[Tuple[int, int, int], List[Tuple[int, int, str, Tuple[float, float]]]]" = OrderedDict()
_TILE_LABEL_CACHE_MAX = 64


# Class → rank table. ``rank`` is the importance ordering when sorting
# candidates and as a fallback for min_zoom. The value list is much
# more permissive than the old version: we accept ``region``,
# ``province``, ``county`` (which Protomaps uses for US-style state-
# level divisions) at rank 1, and treat unknown classes as rank 5
# (mid-importance) instead of rank 9 (lowest) so they don't get
# auto-filtered at every zoom.
_CLASS_RANK = {
    "country": 0,
    "region": 1, "province": 1, "state": 1, "county": 1,
    "city": 2, "metropolis": 2,
    "town": 3, "borough": 3,
    "village": 4,
    "suburb": 5, "quarter": 5, "neighbourhood": 5, "neighborhood": 5,
    "locality": 6, "hamlet": 6,
    "island": 4, "islet": 7,
    "continent": 0,
}


# Fallback min_zoom table keyed on rank. Used when a feature has no
# explicit pmap:min_zoom property. Tuned to be moderately permissive:
# countries appear at world-scale zoom, hamlets only at street-scale.
_FALLBACK_MIN_ZOOM_BY_RANK = {
    0: 1,    # country: visible from world view
    1: 4,    # state/region: visible from continent view
    2: 6,    # city: visible from country view
    3: 8,    # town: visible from regional view
    4: 9,    # village: visible from local-area view
    5: 11,   # suburb/neighbourhood: visible from city view
    6: 12,   # locality/hamlet: visible from neighbourhood view
    7: 13,
    8: 14,
    9: 15,
}


def _extract_labels(tile) -> List[Tuple[int, int, str, Tuple[float, float]]]:
    """Pull (rank, min_zoom, name, tile_local_xy) from a tile's place
    layers.

    Returns a list of label candidates ordered by rank ascending.
    Cached by (z, x, y) since tile data doesn't change once decoded.

    ``min_zoom`` is read directly from ``pmap:min_zoom`` when the
    feature has it; otherwise we fall back to a rank-keyed table. This
    is the primary filter at render time — labels with ``min_zoom > z``
    never get stamped at view zoom ``z``.
    """
    key = (tile.z, tile.x, tile.y)
    if key in _TILE_LABEL_CACHE:
        _TILE_LABEL_CACHE.move_to_end(key)
        return _TILE_LABEL_CACHE[key]

    out: List[Tuple[int, int, str, Tuple[float, float]]] = []
    for layer_name, layer in tile.layers.items():
        if layer_name not in _PLACE_LAYERS:
            continue
        for feat in layer.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            props = feat.get("properties") or {}
            name = (props.get("name:latin") or props.get("name") or
                    props.get("name:en") or "")
            if not name:
                continue
            kind = (props.get("class") or props.get("kind") or
                    props.get("pmap:kind") or "").lower()
            rank = _CLASS_RANK.get(kind, 5)   # default rank: mid (was 9)
            # pmap:rank, when present, overrides the class-based rank.
            pmap_rank = props.get("pmap:rank")
            if isinstance(pmap_rank, (int, float)):
                rank = int(pmap_rank)

            # min_zoom: use the data when present, fall back to
            # rank table when not. Some sources call it min_zoom
            # without the pmap: prefix.
            min_zoom_raw = (props.get("pmap:min_zoom")
                            or props.get("min_zoom"))
            if isinstance(min_zoom_raw, (int, float)):
                min_zoom = int(min_zoom_raw)
            else:
                min_zoom = _FALLBACK_MIN_ZOOM_BY_RANK.get(rank, 10)

            cx, cy = geom["coordinates"]
            out.append((rank, min_zoom, str(name), (float(cx), float(cy))))

    out.sort(key=lambda t: t[0])
    _TILE_LABEL_CACHE[key] = out
    if len(_TILE_LABEL_CACHE) > _TILE_LABEL_CACHE_MAX:
        _TILE_LABEL_CACHE.popitem(last=False)
    return out
    return out


def clear_classify_cache() -> None:
    """Drop the per-tile label cache. Call when switching map sources
    so a tile cached from the old source doesn't bleed into the new
    one."""
    _TILE_LABEL_CACHE.clear()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _rgb_to_style(rgb: Tuple[int, int, int], bold: bool = False) -> str:
    r, g, b = rgb
    bold_str = " bold" if bold else ""
    return f"fg:#{r:02x}{g:02x}{b:02x}{bold_str}"


def apply_vector_overlay(
    rows: FrameFrag,
    vector_source,
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    style,
    pmap_min_zoom: int = 0,
    pmap_max_zoom: int = 15,
    max_labels: int = 64,
    label_bg: bool = True,
) -> int:
    """Stamp place labels into ``rows`` after the basemap renders.

    Reads tiles for the current view, extracts (rank, min_zoom, name,
    position) candidates, projects each to terminal cell coords, and
    stamps the name as text. Three filtering passes are applied:

      1. **Data-driven min_zoom** filter. Each feature carries (or
         is assigned) a ``min_zoom`` value; we skip anything with
         ``min_zoom > z``. Protomaps tiles set ``pmap:min_zoom`` per
         feature based on what the cartographer wants visible at
         what zoom — far more accurate than a hand-coded rank table.

      2. **Spatial dedup** by exact (name, cell_x, cell_y). Adjacent
         tiles sometimes duplicate the same place along their shared
         edge; this catches obvious duplicates while letting two
         genuinely different places with the same name (eg
         "Springfield, MA" and "Springfield, IL") both render.

      3. **Collision avoidance**. Each placed label reserves a
         rectangle so labels don't visually bleed together.

    Returns the count of labels actually stamped.

    With ``label_bg=True`` (default), each text cell gets a bg color
    chosen as the inverse of ``style.label_color`` — readable in any
    theme without needing the user to configure it. The bg is
    applied **only on the cells the text occupies**, not on the
    surrounding cells. So a "Concord" label looks like 7 colored
    cells with letters in them, embedded in the map; the basemap
    shows through right up to each letter.

    With ``label_bg=False``, only the fg color is set. Labels may
    blur into bright basemap cells in this mode — useful if you want
    completely transparent labels and have a label color that
    contrasts well with your typical basemap content.

    Failure to fetch tiles is silent: no tiles → no stamping → caller
    sees the basemap unchanged.
    """
    if vector_source is None:
        return 0

    # Determine which tiles intersect the view.
    fetch_z = max(pmap_min_zoom, min(pmap_max_zoom, z))
    scale = 2 ** (z - fetch_z)
    tile_size_px = 256.0 * scale

    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    canvas_left_world_px = cn_tx * 256.0 - canvas_px_w / 2.0
    canvas_top_world_px = cn_ty * 256.0 - canvas_px_h / 2.0
    canvas_right_world_px = canvas_left_world_px + canvas_px_w
    canvas_bot_world_px = canvas_top_world_px + canvas_px_h

    f_left = canvas_left_world_px / 256.0 / scale
    f_right = canvas_right_world_px / 256.0 / scale
    f_top = canvas_top_world_px / 256.0 / scale
    f_bot = canvas_bot_world_px / 256.0 / scale

    n_tiles = 2 ** fetch_z
    tx_min = max(0, math.floor(f_left))
    tx_max = min(n_tiles - 1, math.floor(f_right))
    ty_min = max(0, math.floor(f_top))
    ty_max = min(n_tiles - 1, math.floor(f_bot))

    # Pre-compute pixel-per-cell ratios for the projection arithmetic.
    px_per_cell_x = canvas_px_w / max(1, term_w)
    px_per_cell_y = canvas_px_h / max(1, term_h)

    # Collect every label candidate from every tile in the viewport.
    # Spatial dedup key is (name, exact cell_x, exact cell_y) — only
    # exact-position duplicates get caught. The previous 3-cell
    # quantum was killing nearby distinct places, e.g. two adjacent
    # towns at low zoom that happen to project within 3 cells of
    # each other.
    seen_keys: set = set()
    candidates: List[Tuple[int, int, int, int, str]] = []
    # tuple = (rank, min_zoom, start_x, cell_y, text)
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            try:
                tile = vector_source.get_tile(fetch_z, tx, ty)
            except Exception:
                continue
            if tile is None:
                continue
            tile_extent = tile.extent or 4096
            tile_world_x = tx * tile_size_px
            tile_world_y = ty * tile_size_px
            tile_origin_cell_x = (tile_world_x - canvas_left_world_px) / px_per_cell_x
            tile_origin_cell_y = (tile_world_y - canvas_top_world_px) / px_per_cell_y
            cells_per_ext_x = (tile_size_px / max(1, tile_extent)) / px_per_cell_x
            cells_per_ext_y = (tile_size_px / max(1, tile_extent)) / px_per_cell_y

            for rank, min_zoom, name, (lx_ext, ly_ext) in _extract_labels(tile):
                # Data-driven zoom visibility filter. Labels tagged
                # for higher zoom levels don't appear at low zoom.
                if min_zoom > z:
                    continue
                cell_x_f = tile_origin_cell_x + lx_ext * cells_per_ext_x
                cell_y_f = tile_origin_cell_y + ly_ext * cells_per_ext_y
                cell_x = int(round(cell_x_f))
                cell_y = int(round(cell_y_f))
                # Truncate long names so a giant city label doesn't push
                # half the row off-screen. 24 chars is plenty for any
                # real place name.
                text = name[:24]
                # Center the label horizontally on the point.
                start_x = cell_x - len(text) // 2
                # Edge culling: text itself must fit on-screen.
                # We use the text's own bounds — there's no halo
                # padding to worry about any more, the bg color is
                # only on the text cells themselves.
                if start_x < 0 or start_x + len(text) > term_w:
                    continue
                if cell_y < 0 or cell_y >= term_h:
                    continue
                # Spatial dedup: exact cell match only.
                key = (name, cell_x, cell_y)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append((rank, min_zoom, start_x, cell_y, text))

    if not candidates:
        return 0

    # Sort by rank (countries > states > cities > towns ...) so the
    # most important labels get first dibs on viewport real estate.
    candidates.sort(key=lambda t: (t[0], t[1]))

    # Build the label text style. When label_bg is on, the text cells
    # get a bg color that's the inverse of the fg — guaranteed
    # readable in any theme. When off, just fg color.
    if label_bg:
        bg = _inverse_color(style.label_color)
        label_style = _rgb_to_style_with_bg(style.label_color, bg, bold=True)
    else:
        label_style = _rgb_to_style(style.label_color, bold=True)

    # Place labels with collision avoidance. Collision rectangle is
    # 1-cell padded on every side so two labels never end up touching
    # — even though the text-cells-only approach means we don't
    # stamp anything in those padding cells, leaving zero visual
    # space between labels would still produce hard-to-read clumps.
    placed: List[Tuple[int, int, int, int]] = []  # x0, y0, x1, y1
    stamped = 0
    for rank, min_zoom, sx_l, sy_l, text in candidates:
        if stamped >= max_labels:
            break
        # Collision rectangle: 1-cell padded on every side so the
        # label has visual breathing room from neighbours even
        # though we don't draw into the padding cells.
        x0 = sx_l - 1
        y0 = sy_l - 1
        x1 = sx_l + len(text)
        y1 = sy_l + 1
        collision = False
        for ox_b, oy_b, ex_b, ey_b in placed:
            if not (x1 < ox_b or x0 > ex_b or y1 < oy_b or y0 > ey_b):
                collision = True
                break
        if collision:
            continue

        # Stamp ONLY the text cells. Surrounding cells (above, below,
        # flanks) keep whatever the basemap drew — this is the
        # "text-cells-only" approach: no rectangle around the label,
        # the basemap shows through right up to each letter.
        _stamp_label(rows, term_w, sx_l, sy_l, text, label_style)
        placed.append((x0, y0, x1, y1))
        stamped += 1

    return stamped


def _inverse_color(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Return a high-contrast bg color for the given fg color.

    Strategy: pick black or near-black if the fg is bright, white or
    near-white if the fg is dark. This isn't true RGB inversion (which
    can produce muddy mid-grays for mid-bright fgs); it's a binary
    luminance threshold which gives visually crisp results.

    The "near-black" #101010 / "near-white" #f0f0f0 choices keep some
    margin from pure values so the text reads as printed-on-paper
    rather than glowing. Slightly less harsh than #000/#fff.
    """
    r, g, b = rgb
    # Luminance per BT.709, integer-arithmetic.
    luma = (2126 * r + 7152 * g + 722 * b) // 10000
    if luma >= 128:
        return (16, 16, 16)
    return (240, 240, 240)


def _max_rank_for_zoom(z: int) -> int:
    """Legacy hand-coded rank cutoff. No longer used by
    ``apply_vector_overlay`` — the overlay now reads ``min_zoom``
    directly from feature properties (or falls back to a per-rank
    table inside ``_extract_labels``). Kept here for any external
    code that imported it; will be removed in a future patch.

    Returns the highest rank value previously emitted at zoom ``z``.
    """
    if z < 4:
        return 0
    if z < 6:
        return 1
    if z < 8:
        return 2
    if z < 10:
        return 3
    if z < 12:
        return 6
    return 9


def _rgb_to_style_with_bg(
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    bold: bool = False,
) -> str:
    """Build a prompt_toolkit style string with both fg and bg set."""
    bold_str = " bold" if bold else ""
    return (
        f"bg:#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x} "
        f"fg:#{fg[0]:02x}{fg[1]:02x}{fg[2]:02x}{bold_str}"
    )
