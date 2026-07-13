
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

_PLACE_LAYERS = {"places", "place_labels", "place"}

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
    if vector_source is None:
        return 0

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
                if min_zoom > z:
                    continue
                cell_x_f = tile_origin_cell_x + lx_ext * cells_per_ext_x
                cell_y_f = tile_origin_cell_y + ly_ext * cells_per_ext_y
                cell_x = int(round(cell_x_f))
                cell_y = int(round(cell_y_f))
                text = name[:24]
                start_x = cell_x - len(text) // 2
                if start_x < 0 or start_x + len(text) > term_w:
                    continue
                if cell_y < 0 or cell_y >= term_h:
                    continue
                key = (name, cell_x, cell_y)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                candidates.append((rank, min_zoom, start_x, cell_y, text))

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
