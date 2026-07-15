from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from cartotui.geodesy import latlon_to_tile_xy
from cartotui.vector_source import VectorTile, VectorTileSource

log = logging.getLogger("cartotui.raster_v")

_LOG_DEDUPE: set = set()

__all__ = ["rasterise_view", "ROAD_CLASS_PRIORITY", "VectorStyle", "default_style"]

ROAD_CLASS_PRIORITY: Dict[str, int] = {
    "highway":      10,
    "motorway":     10,
    "trunk":        9,
    "primary":      8,
    "secondary":    7,
    "tertiary":     6,
    "minor_road":   5,
    "residential":  4,
    "street":       4,
    "service":      3,
    "path":         2,
    "footway":      2,
    "cycleway":     2,
    "track":        2,
    "other":        1,
}

_MIN_POLY_PX = 2.0
_MIN_LINE_PX = 3.0

@dataclass
class VectorStyle:

    bg:       Tuple[int, int, int] = (15, 15, 20)
    water:    Tuple[int, int, int] = (95, 105, 120)
    park:     Tuple[int, int, int] = (60, 80, 60)
    building: Tuple[int, int, int] = (75, 75, 80)
    road_color: Tuple[int, int, int] = (255, 255, 255)
    label_color: Tuple[int, int, int] = (255, 255, 255)
    halo_color:  Tuple[int, int, int] = (0, 0, 0)

    aircraft_color:          Tuple[int, int, int] = (255, 200, 60)
    aircraft_selected_color: Tuple[int, int, int] = (255, 255, 255)
    aircraft_emergency_color: Tuple[int, int, int] = (255, 80, 80)
    aircraft_label_color:    Tuple[int, int, int] = (255, 220, 120)
    aircraft_halo_color:     Tuple[int, int, int] = (0, 0, 0)

    road_widths: Dict[int, int] = None
    road_colors: Dict[int, Tuple[int, int, int]] = None

    draw_labels: bool = False

    def __post_init__(self):
        if self.road_widths is None:
            self.road_widths = {
                10: 9,
                9:  8,
                8:  7,
                7:  6,
                6:  5,
                5:  5,
                4:  4,
                3:  4,
                2:  4,
                1:  4,
            }
        if self.road_colors is None:
            self.road_colors = {
                10: (255, 255, 255),
                9:  (245, 245, 245),
                8:  (230, 230, 230),
                7:  (210, 210, 210),
                6:  (195, 195, 195),
                5:  (175, 175, 175),
                4:  (160, 160, 160),
                3:  (140, 140, 140),
                2:  (120, 120, 120),
                1:  (110, 110, 110),
            }

    def color_for_priority(self, priority: int) -> Tuple[int, int, int]:
        return self.road_colors.get(priority, self.road_color)

def default_style(theme: str = "amber") -> VectorStyle:
    from cartotui.themes import theme_vector_style
    return theme_vector_style(theme)

def rasterise_view(
    source: VectorTileSource,
    lat: float,
    lon: float,
    z: int,
    width_px: int,
    height_px: int,
    style: Optional[VectorStyle] = None,
    overzoom: int = 2,
    pmap_min_zoom: int = 0,
    pmap_max_zoom: int = 15,
    aircraft_overlay: Optional[Iterable] = None,
    selected_icao: Optional[str] = None,
    supersample: float = 1.0,
    road_thickness: float = 1.0,
) -> Image.Image:

    style = style or default_style()
    width_px = max(1, int(width_px))
    height_px = max(1, int(height_px))

    fetch_z = min(max(z, pmap_min_zoom), pmap_max_zoom)
    scale = 2 ** (z - fetch_z)

    xt, yt = latlon_to_tile_xy(lat, lon, z)
    extent = 4096
    tile_size_px = 256.0 * scale

    cx_px = width_px / 2.0
    cy_px = height_px / 2.0

    world_left_px = (xt * 256.0) - cx_px
    world_top_px = (yt * 256.0) - cy_px
    world_right_px = world_left_px + width_px
    world_bot_px = world_top_px + height_px

    f_left = world_left_px / 256.0 / scale
    f_top  = world_top_px  / 256.0 / scale
    f_right = world_right_px / 256.0 / scale
    f_bot   = world_bot_px   / 256.0 / scale

    n = 2 ** fetch_z
    tx_min = max(0, math.floor(f_left))
    tx_max = min(n - 1, math.floor(f_right))
    ty_min = max(0, math.floor(f_top))
    ty_max = min(n - 1, math.floor(f_bot))

    img = Image.new("RGB", (width_px, height_px), style.bg)
    draw = ImageDraw.Draw(img, "RGB")

    tiles: List[Tuple[VectorTile, float, float, float]] = []
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            tile = source.get_tile(fetch_z, tx, ty)
            if tile is None:
                continue
            tile_screen_x = tx * tile_size_px - world_left_px
            tile_screen_y = ty * tile_size_px - world_top_px
            px_per_ext = tile_size_px / float(tile.extent or extent)
            tiles.append((tile, tile_screen_x, tile_screen_y, px_per_ext))

    if not tiles:
        sig = ("no_tiles", fetch_z, round(lat, 2), round(lon, 2))
        if sig not in _LOG_DEDUPE:
            _LOG_DEDUPE.add(sig)
            log.warning(
                "rasterise_view: 0 tiles loaded for view at z=%d (%.4f,%.4f); "
                "vector source returning None — check API key / network / source URL",
                z, lat, lon,
            )
    elif log.isEnabledFor(logging.DEBUG):
        layer_summary = {}
        for tile, _sx, _sy, _ppe in tiles:
            for lname, layer in tile.layers.items():
                layer_summary[lname] = layer_summary.get(lname, 0) + len(
                    layer.get("features", [])
                )
        log.debug(
            "rasterise_view: %d tiles, layers/features: %s",
            len(tiles),
            ", ".join(f"{k}={v}" for k, v in sorted(layer_summary.items())),
        )

    road_scale = min(0.55, max(0.125, 0.125 + (z - 9) * 0.0625))
    road_scale *= max(1.0, float(supersample))
    road_scale *= max(0.05, float(road_thickness))
    min_road_prio = min(10, max(1, 18 - z))
    _draw_water_and_landuse(draw, tiles, style)
    _draw_roads(draw, tiles, style, road_scale, min_road_prio)
    if style.draw_labels:
        _draw_labels(draw, tiles, style, width_px, height_px)
    if aircraft_overlay:
        _draw_aircraft(
            draw,
            aircraft_overlay,
            z=z,
            world_left_px=world_left_px,
            world_top_px=world_top_px,
            width_px=width_px,
            height_px=height_px,
            style=style,
            selected_icao=(selected_icao.upper() if selected_icao else None),
        )

    return img

def _xform_geom(
    coords,
    sx: float,
    sy: float,
    px_per_ext: float,
):
    if not coords:
        return coords
    first = coords[0]
    if isinstance(first, (int, float)):
        return (sx + coords[0] * px_per_ext, sy + coords[1] * px_per_ext)
    return [_xform_geom(c, sx, sy, px_per_ext) for c in coords]

def _flatten_lines(coords) -> Iterable[List[Tuple[float, float]]]:
    if not coords:
        return
    first = coords[0]
    if isinstance(first, tuple) and len(first) == 2 and isinstance(first[0], (int, float)):
        yield list(coords)
        return
    if isinstance(first, list) and first and isinstance(first[0], (int, float)):
        yield [tuple(p) for p in coords]
        return
    for sub in coords:
        yield from _flatten_lines(sub)

def _flatten_polygons(coords) -> Iterable[List[Tuple[float, float]]]:
    if not coords:
        return
    first = coords[0]
    if first and isinstance(first[0], tuple):
        yield [tuple(p) for p in first]
        return
    if first and isinstance(first[0], list):
        for poly in coords:
            if poly and isinstance(poly[0], (list, tuple)):
                ring = poly[0]
                if ring and isinstance(ring[0], tuple):
                    yield [tuple(p) for p in ring]

def _bbox_extent_diag(coords) -> Tuple[float, float]:
    if not coords:
        return (0.0, 0.0)
    first = coords[0]
    if not first:
        return (0.0, 0.0)

    if isinstance(first[0], (int, float)):
        min_x = max_x = first[0]
        min_y = max_y = first[1]
        for p in coords:
            x, y = p[0], p[1]
            if x < min_x: min_x = x
            elif x > max_x: max_x = x
            if y < min_y: min_y = y
            elif y > max_y: max_y = y
        return (max_x - min_x, max_y - min_y)

    if isinstance(first[0][0], (int, float)):
        ring = first
        min_x = max_x = ring[0][0]
        min_y = max_y = ring[0][1]
        for p in ring:
            x, y = p[0], p[1]
            if x < min_x: min_x = x
            elif x > max_x: max_x = x
            if y < min_y: min_y = y
            elif y > max_y: max_y = y
        return (max_x - min_x, max_y - min_y)

    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for poly in coords:
        if not poly:
            continue
        ring = poly[0]
        if not ring:
            continue
        for p in ring:
            x, y = p[0], p[1]
            if x < min_x: min_x = x
            elif x > max_x: max_x = x
            if y < min_y: min_y = y
            elif y > max_y: max_y = y
    if min_x == float("inf"):
        return (0.0, 0.0)
    return (max_x - min_x, max_y - min_y)

_WATER_LAYER_NAMES = {"water", "ocean", "rivers", "lakes",
                      "water_polygons", "water_lines"}
_LANDUSE_LAYER_NAMES = {"landuse", "landcover", "natural",
                        "land", "sites"}
_PARK_KINDS = {"park", "wood", "forest", "grass", "playground", "garden",
               "nature_reserve", "meadow", "recreation_ground", "cemetery",
               "allotments", "golf_course", "pitch", "village_green"}
_BUILDING_LAYERS = {"buildings", "building"}
_ROAD_LAYERS = {"roads", "transportation",
                "streets", "bridges"}
_PLACE_LAYERS = {"places", "place_labels"}

def _draw_water_and_landuse(draw, tiles, style):
    skipped_bldg = 0
    drawn_bldg = 0
    for tile, sx, sy, px_per_ext in tiles:
        ext_thresh = _MIN_POLY_PX / px_per_ext if px_per_ext > 0 else 0.0
        check_size = ext_thresh > 1.0

        for layer_name in _WATER_LAYER_NAMES:
            layer = tile.layers.get(layer_name)
            if not layer:
                continue
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                if check_size:
                    ew, eh = _bbox_extent_diag(geom["coordinates"])
                    if ew < ext_thresh and eh < ext_thresh:
                        continue
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=style.water)
                        except Exception:
                            pass

        for layer_name in _LANDUSE_LAYER_NAMES:
            layer = tile.layers.get(layer_name)
            if not layer:
                continue
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                props = feat.get("properties") or {}
                kind = (props.get("class") or props.get("kind") or
                        props.get("pmap:kind") or props.get("type") or "").lower()
                fill = style.park if kind in _PARK_KINDS else None
                if fill is None:
                    continue
                if check_size:
                    ew, eh = _bbox_extent_diag(geom["coordinates"])
                    if ew < ext_thresh and eh < ext_thresh:
                        continue
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=fill)
                        except Exception:
                            pass

        for layer_name in _BUILDING_LAYERS:
            layer = tile.layers.get(layer_name)
            if not layer:
                continue
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                if check_size:
                    ew, eh = _bbox_extent_diag(geom["coordinates"])
                    if ew < ext_thresh and eh < ext_thresh:
                        skipped_bldg += 1
                        continue
                drawn_bldg += 1
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=style.building)
                        except Exception:
                            pass

    if log.isEnabledFor(logging.DEBUG) and (drawn_bldg + skipped_bldg) > 0:
        log.debug(
            "buildings: drew %d, skipped %d sub-pixel",
            drawn_bldg, skipped_bldg,
        )

def _draw_roads(draw, tiles, style, road_scale: float = 1.0,
                min_road_prio: int = 1):
    items: List[Tuple[int, float, float, float, dict, dict]] = []
    skipped = 0
    for tile, sx, sy, px_per_ext in tiles:
        max_road_w = 1
        for w in style.road_widths.values():
            if w > max_road_w:
                max_road_w = w
        line_thresh_px = max(_MIN_LINE_PX, max_road_w * 0.5)
        ext_thresh = line_thresh_px / px_per_ext if px_per_ext > 0 else 0.0
        check_size = ext_thresh > 1.0

        for layer_name in _ROAD_LAYERS:
            layer = tile.layers.get(layer_name)
            if not layer:
                continue
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("LineString", "MultiLineString"):
                    continue
                props = feat.get("properties") or {}
                cls = (props.get("class") or props.get("kind") or
                       props.get("pmap:kind") or "other").lower()
                priority = ROAD_CLASS_PRIORITY.get(cls, 1)
                if priority < min_road_prio:
                    skipped += 1
                    continue
                width = max(1, int(round(style.road_widths.get(priority, 1) * road_scale)))
                if check_size:
                    per_class_thresh = max(_MIN_LINE_PX, width * 0.5) / px_per_ext
                    ew, eh = _bbox_extent_diag(geom["coordinates"])
                    if max(ew, eh) < per_class_thresh:
                        skipped += 1
                        continue
                items.append((priority, sx, sy, px_per_ext, geom, props))

    items.sort(key=lambda t: t[0])

    for priority, sx, sy, px_per_ext, geom, _props in items:
        width = max(1, int(round(style.road_widths.get(priority, 1) * road_scale)))
        color = style.color_for_priority(priority)
        xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
        for line in _flatten_lines(xformed):
            if len(line) < 2:
                continue
            try:
                draw.line(line, fill=color, width=width)
            except Exception:
                pass

    if log.isEnabledFor(logging.DEBUG) and (len(items) + skipped) > 0:
        log.debug("roads: drew %d, skipped %d sub-width", len(items), skipped)

def _draw_labels(draw, tiles, style, w: int, h: int):
    candidates: List[Tuple[int, float, float, str]] = []
    for tile, sx, sy, px_per_ext in tiles:
        for layer_name in _PLACE_LAYERS:
            layer = tile.layers.get(layer_name)
            if not layer:
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
                rank_map = {"country": 0, "state": 1, "city": 2, "town": 3,
                            "village": 4, "suburb": 5, "neighbourhood": 6,
                            "neighborhood": 6, "locality": 7, "hamlet": 8}
                rank = rank_map.get(kind, 9)
                pmap_rank = props.get("pmap:rank")
                if isinstance(pmap_rank, (int, float)):
                    rank = int(pmap_rank)
                cx, cy = geom["coordinates"]
                px = sx + cx * px_per_ext
                py = sy + cy * px_per_ext
                if 0 <= px < w and 0 <= py < h:
                    candidates.append((rank, px, py, name))

    if not candidates:
        return
    candidates.sort(key=lambda t: t[0])

    placed: List[Tuple[float, float, float, float]] = []
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    char_w, char_h = 6, 11

    def overlaps(box, others):
        x0, y0, x1, y1 = box
        for ox0, oy0, ox1, oy1 in others:
            if not (x1 < ox0 or x0 > ox1 or y1 < oy0 or y0 > oy1):
                return True
        return False

    for _rank, px, py, name in candidates[:200]:
        text = name[:32]
        tw = char_w * len(text)
        th = char_h
        x0 = px - tw / 2
        y0 = py - th / 2
        x1 = x0 + tw
        y1 = y0 + th
        if x0 < 0 or y0 < 0 or x1 >= w or y1 >= h:
            continue
        if overlaps((x0 - 4, y0 - 2, x1 + 4, y1 + 2), placed):
            continue
        if font is not None:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (1, -1), (-1, 1), (1, 1)):
                try:
                    draw.text((x0 + dx, y0 + dy), text, fill=style.halo_color, font=font)
                except Exception:
                    pass
            try:
                draw.text((x0, y0), text, fill=style.label_color, font=font)
            except Exception:
                pass
        placed.append((x0 - 4, y0 - 2, x1 + 4, y1 + 2))

_LAST_HITBOXES: List[Tuple[str, float, float, float, float]] = []

def last_aircraft_hitboxes() -> List[Tuple[str, float, float, float, float]]:
    return list(_LAST_HITBOXES)

def _aircraft_canvas_xy(
    lat: float, lon: float, z: int,
    world_left_px: float, world_top_px: float,
) -> Tuple[float, float]:
    tx, ty = latlon_to_tile_xy(lat, lon, z)
    wx = tx * 256.0
    wy = ty * 256.0
    return (wx - world_left_px, wy - world_top_px)

def _aircraft_marker(
    draw,
    cx: float, cy: float,
    track_deg: Optional[float],
    color: Tuple[int, int, int],
    halo: Tuple[int, int, int],
    size: int,
):
    if track_deg is None:
        r = size
        try:
            draw.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=halo)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        except Exception:
            pass
        return

    a = math.radians(track_deg)
    sin_a, cos_a = math.sin(a), math.cos(a)
    pts = [(0.0, -size * 1.4), (size * 0.9, size * 0.8), (-size * 0.9, size * 0.8)]

    def rot(p):
        x, y = p
        rx = x * cos_a - y * sin_a
        ry = x * sin_a + y * cos_a
        return (cx + rx, cy + ry)

    poly = [rot(p) for p in pts]
    try:
        halo_poly = [
            (cx + (px - cx) * 1.25, cy + (py - cy) * 1.25) for px, py in poly
        ]
        draw.polygon(halo_poly, fill=halo)
        draw.polygon(poly, fill=color)
    except Exception:
        pass

def _draw_aircraft(
    draw,
    aircraft_iter,
    z: int,
    world_left_px: float,
    world_top_px: float,
    width_px: int,
    height_px: int,
    style: VectorStyle,
    selected_icao: Optional[str] = None,
):
    global _LAST_HITBOXES
    _LAST_HITBOXES = []

    font = None
    try:
        font = ImageFont.load_default()
    except Exception:
        pass

    marker_size = max(4, min(10, 4 + z // 3))

    margin = marker_size * 4

    items = []
    selected_item = None
    for ac in aircraft_iter:
        if not ac.has_position():
            continue
        cx, cy = _aircraft_canvas_xy(
            ac.lat, ac.lon, z, world_left_px, world_top_px,
        )
        if cx < -margin or cy < -margin:
            continue
        if cx >= width_px + margin or cy >= height_px + margin:
            continue
        is_selected = (selected_icao is not None and ac.icao.upper() == selected_icao)
        if ac.emergency:
            color = style.aircraft_emergency_color
        elif is_selected:
            color = style.aircraft_selected_color
        else:
            color = style.aircraft_color
        entry = (ac, cx, cy, color, is_selected)
        if is_selected:
            selected_item = entry
        else:
            items.append(entry)

    if selected_item is not None:
        items.append(selected_item)

    for ac, cx, cy, color, is_selected in items:
        size = marker_size + (2 if is_selected else 0)
        _aircraft_marker(
            draw, cx, cy, ac.track_deg, color, style.aircraft_halo_color, size,
        )

        if font is not None and (is_selected or marker_size >= 6):
            label = ac.display_label()
            if label:
                lx = cx + size + 2
                ly = cy - size
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    try:
                        draw.text(
                            (lx + dx, ly + dy), label,
                            fill=style.aircraft_halo_color, font=font,
                        )
                    except Exception:
                        pass
                try:
                    draw.text(
                        (lx, ly), label,
                        fill=style.aircraft_label_color, font=font,
                    )
                except Exception:
                    pass

        hb = (size + 2) * 1.5
        _LAST_HITBOXES.append(
            (ac.icao, cx - hb, cy - hb, cx + hb, cy + hb)
        )
