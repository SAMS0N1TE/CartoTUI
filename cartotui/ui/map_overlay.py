
from __future__ import annotations

import logging
import math
from collections import OrderedDict
from typing import List, Optional, Tuple

from cartotui.admin1 import TILE_ADMIN1_MIN_Z, admin1_lines
from cartotui.geodesy import latlon_to_tile_xy

log = logging.getLogger("cartotui.overlay")
_LAYERS_LOGGED: set = set()
from cartotui.ui.aircraft_overlay import (
    _stamp_cells_batch,
    _stamp_label,
)

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

_PLACE_LAYERS = {"places", "place_labels", "place"}
_ADMIN_LABEL_LAYERS = {"boundary_labels", "admin_labels", "place_labels_admin"}

_BOUNDARY_LAYERS = {"boundaries", "boundary", "admin", "admin_boundaries"}
_BOUNDARY_LEVELS = {
    2: 2,
    3: 4,
    4: 4,
}

def _boundary_glyph(x0: int, y0: int, x1: int, y1: int,
                    level: int, mode: str) -> str:
    if mode == "dots":
        return "•" if level == 2 else "·"
    if mode == "dashed":
        return "═" if level == 2 else ("─" if level == 3 else "╌")
    dx = x1 - x0
    dy = y1 - y0
    heavy = (level == 2)
    if abs(dx) >= 2 * abs(dy):
        return "═" if heavy else "─"
    if abs(dy) >= 2 * abs(dx):
        return "║" if heavy else "│"
    return "╲" if (dx > 0) == (dy > 0) else "╱"
_CLASS_TO_ADMIN_LEVEL = {
    "country": 2, "nation": 2,
    "state": 4, "region": 4, "province": 4, "territory": 4,
}

def _admin_level(props: dict) -> Optional[int]:
    raw = props.get("admin_level")
    if raw is None:
        kind = str(props.get("class") or props.get("kind")
                   or props.get("pmap:kind") or "").lower()
        return _CLASS_TO_ADMIN_LEVEL.get(kind)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None

def _iter_line_coords(coords):
    """Yield each LineString as a flat list of (x, y) from a (Multi)LineString."""
    if not coords:
        return
    first = coords[0]
    if isinstance(first, (int, float)):
        return
    if isinstance(first[0], (int, float)):
        yield list(coords)
        return
    for part in coords:
        yield from _iter_line_coords(part)

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
    ac_tx, ac_ty = latlon_to_tile_xy(lat, lon, z)
    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    cells_per_tile_x = 256.0 * term_w / max(1, canvas_px_w)
    cells_per_tile_y = 256.0 * term_h / max(1, canvas_px_h)
    cx = term_w / 2.0 + (ac_tx - cn_tx) * cells_per_tile_x
    cy = term_h / 2.0 + (ac_ty - cn_ty) * cells_per_tile_y
    return cx, cy

_TILE_LABEL_CACHE: "OrderedDict[Tuple[int, int, int], List[Tuple[int, int, str, Tuple[float, float]]]]" = OrderedDict()
_TILE_LABEL_CACHE_MAX = 64

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

_FALLBACK_MIN_ZOOM_BY_RANK = {
    0: 1,
    1: 4,
    2: 6,
    3: 8,
    4: 9,
    5: 11,
    6: 12,
    7: 13,
    8: 14,
    9: 15,
}

def _extract_labels(tile) -> List[Tuple[int, int, str, Tuple[float, float]]]:
    key = (tile.z, tile.x, tile.y)
    if key in _TILE_LABEL_CACHE:
        _TILE_LABEL_CACHE.move_to_end(key)
        return _TILE_LABEL_CACHE[key]

    out: List[Tuple[int, int, str, Tuple[float, float]]] = []
    for layer_name, layer in tile.layers.items():
        is_admin = layer_name in _ADMIN_LABEL_LAYERS
        if layer_name not in _PLACE_LAYERS and not is_admin:
            continue
        for feat in layer.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            props = feat.get("properties") or {}
            name = (props.get("name:latin") or props.get("name") or
                    props.get("name:en") or props.get("name_en") or "")
            if not name:
                continue

            if is_admin:
                level = _admin_level(props)
                if level is None or level > 4:
                    continue
                rank = 0 if level <= 2 else 1
            else:
                kind = (props.get("class") or props.get("kind") or
                        props.get("pmap:kind") or "").lower()
                rank = _CLASS_RANK.get(kind, 5)
                pmap_rank = props.get("pmap:rank")
                if isinstance(pmap_rank, (int, float)):
                    rank = int(pmap_rank)

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
    _TILE_LABEL_CACHE.clear()

def _rgb_to_style(rgb: Tuple[int, int, int], bold: bool = False) -> str:
    r, g, b = rgb
    bold_str = " bold" if bold else ""
    return f"fg:#{r:02x}{g:02x}{b:02x}{bold_str}"

def _line_cells(x0: int, y0: int, x1: int, y1: int):
    """Integer cells along a segment (Bresenham)."""
    cells = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    guard = 0
    limit = dx - dy + 2
    while True:
        cells.append((x, y))
        if (x == x1 and y == y1) or guard > limit:
            break
        guard += 1
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return cells

def draw_boundary_lines(
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
    max_cells: int = 12000,
    boundary_style: str = "dots",
    admin1_fallback: bool = True,
) -> int:
    if vector_source is None:
        return 0

    fetch_z = max(pmap_min_zoom, min(pmap_max_zoom, z))
    scale = 2 ** (z - fetch_z)
    tile_size_px = 256.0 * scale

    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    canvas_left = cn_tx * 256.0 - canvas_px_w / 2.0
    canvas_top = cn_ty * 256.0 - canvas_px_h / 2.0

    f_left = canvas_left / 256.0 / scale
    f_right = (canvas_left + canvas_px_w) / 256.0 / scale
    f_top = canvas_top / 256.0 / scale
    f_bot = (canvas_top + canvas_px_h) / 256.0 / scale

    n_tiles = 2 ** fetch_z
    tx_min = max(0, math.floor(f_left))
    tx_max = min(n_tiles - 1, math.floor(f_right))
    ty_min = max(0, math.floor(f_top))
    ty_max = min(n_tiles - 1, math.floor(f_bot))

    px_per_cell_x = canvas_px_w / max(1, term_w)
    px_per_cell_y = canvas_px_h / max(1, term_h)

    color = getattr(style, "label_color", (200, 200, 200))
    base_style = f"fg:#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    stamps: List[Tuple[int, int, str, str]] = []
    dash = 0
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            try:
                tile = vector_source.get_tile(fetch_z, tx, ty)
            except Exception:
                continue
            if tile is None:
                continue
            extent = tile.extent or 4096
            origin_cx = (tx * tile_size_px - canvas_left) / px_per_cell_x
            origin_cy = (ty * tile_size_px - canvas_top) / px_per_cell_y
            cells_per_ext_x = (tile_size_px / max(1, extent)) / px_per_cell_x
            cells_per_ext_y = (tile_size_px / max(1, extent)) / px_per_cell_y

            for lname, layer in tile.layers.items():
                if lname not in _BOUNDARY_LAYERS:
                    continue
                for feat in layer.get("features", []):
                    props = feat.get("properties") or {}
                    if props.get("maritime"):
                        continue
                    level = _admin_level(props)
                    min_z = _BOUNDARY_LEVELS.get(level)
                    if min_z is None:
                        continue
                    if z < min_z:
                        continue
                    geom = feat.get("geometry") or {}
                    if geom.get("type") not in ("LineString", "MultiLineString"):
                        continue
                    for line in _iter_line_coords(geom.get("coordinates")):
                        prev = None
                        for (ex, ey) in line:
                            cx = int(round(origin_cx + ex * cells_per_ext_x))
                            cy = int(round(origin_cy + ey * cells_per_ext_y))
                            if prev is not None:
                                glyph = _boundary_glyph(prev[0], prev[1],
                                                        cx, cy, level, boundary_style)
                                for i, (gx, gy) in enumerate(
                                        _line_cells(prev[0], prev[1], cx, cy)):
                                    dash += 1
                                    if boundary_style == "dashed" and dash % 2 == 0:
                                        continue
                                    if 0 <= gx < term_w and 0 <= gy < term_h:
                                        stamps.append((gx, gy, glyph, base_style))
                            prev = (cx, cy)
                        if len(stamps) > max_cells:
                            break

    if admin1_fallback and z < TILE_ADMIN1_MIN_Z:
        stamps.extend(_admin1_stamps(
            z=z, term_w=term_w, term_h=term_h,
            canvas_left=canvas_left, canvas_top=canvas_top,
            px_per_cell_x=px_per_cell_x, px_per_cell_y=px_per_cell_y,
            base_style=base_style, boundary_style=boundary_style,
        ))

    if not stamps:
        return 0
    _stamp_cells_batch(rows, term_w, stamps[:max_cells])
    return len(stamps[:max_cells])

def _admin1_stamps(*, z, term_w, term_h, canvas_left, canvas_top,
                   px_per_cell_x, px_per_cell_y, base_style, boundary_style):
    out: List[Tuple[int, int, str, str]] = []
    margin = 4
    for min_zoom, line in admin1_lines():
        if z < min_zoom:
            continue
        prev = None
        prev_vis = False
        for lon, lat in line:
            try:
                tx, ty = latlon_to_tile_xy(lat, lon, z)
            except (ValueError, ZeroDivisionError):
                prev = None
                continue
            cx = int(round((tx * 256.0 - canvas_left) / px_per_cell_x))
            cy = int(round((ty * 256.0 - canvas_top) / px_per_cell_y))
            vis = (-margin <= cx <= term_w + margin
                   and -margin <= cy <= term_h + margin)
            if prev is not None and (vis or prev_vis):
                glyph = _boundary_glyph(prev[0], prev[1], cx, cy, 4,
                                        boundary_style)
                for gx, gy in _line_cells(prev[0], prev[1], cx, cy):
                    if 0 <= gx < term_w and 0 <= gy < term_h:
                        out.append((gx, gy, glyph, base_style))
            prev = (cx, cy)
            prev_vis = vis
    return out

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
    draw_boundaries: bool = False,
    boundary_style: str = "dots",
) -> int:
    if vector_source is None:
        return 0

    if draw_boundaries:
        try:
            draw_boundary_lines(
                rows, vector_source,
                center_lat=center_lat, center_lon=center_lon, z=z,
                term_w=term_w, term_h=term_h,
                canvas_px_w=canvas_px_w, canvas_px_h=canvas_px_h,
                style=style, pmap_min_zoom=pmap_min_zoom,
                pmap_max_zoom=pmap_max_zoom,
                boundary_style=boundary_style,
            )
        except Exception:
            pass

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

    px_per_cell_x = canvas_px_w / max(1, term_w)
    px_per_cell_y = canvas_px_h / max(1, term_h)

    seen_keys: set = set()
    candidates: List[Tuple[int, int, int, int, str]] = []
    dbg_layers: set = set()
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            try:
                tile = vector_source.get_tile(fetch_z, tx, ty)
            except Exception:
                continue
            if tile is None:
                continue
            if log.isEnabledFor(logging.DEBUG):
                dbg_layers.update(tile.layers.keys())
            tile_extent = tile.extent or 4096
            tile_world_x = tx * tile_size_px
            tile_world_y = ty * tile_size_px
            tile_origin_cell_x = (tile_world_x - canvas_left_world_px) / px_per_cell_x
            tile_origin_cell_y = (tile_world_y - canvas_top_world_px) / px_per_cell_y
            cells_per_ext_x = (tile_size_px / max(1, tile_extent)) / px_per_cell_x
            cells_per_ext_y = (tile_size_px / max(1, tile_extent)) / px_per_cell_y

            for rank, min_zoom, name, (lx_ext, ly_ext) in _extract_labels(tile):
                important = rank <= 1
                gate = min_zoom
                if important:
                    gate = min(gate, _FALLBACK_MIN_ZOOM_BY_RANK.get(rank, gate))
                if gate > z:
                    continue
                cell_x = int(round(tile_origin_cell_x + lx_ext * cells_per_ext_x))
                cell_y = int(round(tile_origin_cell_y + ly_ext * cells_per_ext_y))
                text = name[:24]
                if len(text) > term_w:
                    continue
                margin_y = max(2, term_h // 3) if important else 1
                margin_x = max(4, term_w // 3) if important else 2
                if not (-margin_y <= cell_y < term_h + margin_y):
                    continue
                if not (-margin_x <= cell_x < term_w + margin_x):
                    continue
                cell_y = max(0, min(term_h - 1, cell_y))
                start_x = cell_x - len(text) // 2
                start_x = max(0, min(term_w - len(text), start_x))
                key = (name, cell_x // 4, cell_y // 2)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append((rank, min_zoom, start_x, cell_y, text))

    if log.isEnabledFor(logging.DEBUG) and dbg_layers:
        sig = tuple(sorted(dbg_layers))
        if sig not in _LAYERS_LOGGED:
            _LAYERS_LOGGED.add(sig)
            n_important = sum(1 for c in candidates if c[0] <= 1)
            log.debug("overlay z=%d layers=%s | label candidates=%d (country/state=%d)",
                      z, ", ".join(sig), len(candidates), n_important)

    if not candidates:
        return 0

    candidates.sort(key=lambda t: (t[0], t[1]))

    if label_bg:
        bg = _inverse_color(style.label_color)
        label_style = _rgb_to_style_with_bg(style.label_color, bg, bold=True)
    else:
        label_style = _rgb_to_style(style.label_color, bold=True)

    placed: List[Tuple[int, int, int, int]] = []
    stamped = 0
    for rank, min_zoom, sx_l, sy_l, text in candidates:
        if stamped >= max_labels:
            break
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

        _stamp_label(rows, term_w, sx_l, sy_l, text, label_style)
        placed.append((x0, y0, x1, y1))
        stamped += 1

    return stamped

def _inverse_color(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    r, g, b = rgb
    if r > 160 and (g + b) < r:
        return (16, 16, 16)
    luma = (2126 * r + 7152 * g + 722 * b) // 10000
    if luma >= 128:
        return (16, 16, 16)
    return (240, 240, 240)

def _max_rank_for_zoom(z: int) -> int:
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
    bold_str = " bold" if bold else ""
    return (
        f"bg:#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x} "
        f"fg:#{fg[0]:02x}{fg[1]:02x}{fg[2]:02x}{bold_str}"
    )
