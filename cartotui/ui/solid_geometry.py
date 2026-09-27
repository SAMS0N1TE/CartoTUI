"""SSH-safe geometry: project source lines directly onto terminal cells."""
import math
import weakref
from collections import OrderedDict

import numpy as np

from cartotui.geodesy import latlon_to_tile_xy
from cartotui.rendering.packed import PackedFrame, compile_stamps
from cartotui.ui.aircraft_overlay import _stamp_cells_batch
from cartotui.ui.map_overlay import _iter_line_coords, _line_cells

ROADS = frozenset(("roads", "streets", "transportation", "bridges"))
WATER = frozenset(("water", "water_polygons", "water_lines", "waterway", "ocean", "lakes", "rivers"))
BUILDINGS = frozenset(("buildings", "building"))


def blank_frame(width, height, bg, packed=True):
    color = (bg[0] << 16) | (bg[1] << 8) | bg[2]
    if packed:
        return PackedFrame(np.full((height, width), 32, np.uint32), None,
                           np.full((height, width), color, np.uint32), width, height)
    return [[(f"bg:#{color:06x}", " " * width)] for _ in range(height)]


def clip_segment(x0, y0, x1, y1, width, height):
    """Liang–Barsky clipping bounds work even for deeply overzoomed tiles."""
    dx, dy = x1 - x0, y1 - y0
    low, high = 0., 1.
    for p, q in ((-dx, x0), (dx, width - 1 - x0), (-dy, y0), (dy, height - 1 - y0)):
        if p == 0:
            if q < 0:
                return None
        else:
            t = q / p
            if p < 0:
                low = max(low, t)
            else:
                high = min(high, t)
            if low > high:
                return None
    return tuple(round(v) for v in (x0 + low * dx, y0 + low * dy,
                                    x0 + high * dx, y0 + high * dy))


def _prepared_segments(source, tile, name, layer):
    cache = getattr(source, "_geometry_segments", None)
    if cache is None:
        cache = source._geometry_segments = OrderedDict()
    key = (id(tile), name)
    found = cache.get(key)
    if found and found[0]() is tile:
        cache.move_to_end(key)
        return found[1], found[2]
    raw, gates = [], []
    extent = layer.get("extent") or 4096
    for feat in layer.get("features", []):
        props = feat.get("properties") or {}
        kind = str(props.get("class") or props.get("kind") or props.get("pmap:kind") or "")
        gate = (0 if kind in ("motorway", "trunk", "highway") else 8 if kind == "primary"
                else 13 if kind in ("service", "path", "footway", "track", "steps") else 10) if name in ROADS else 0
        geom = feat.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString", "Polygon", "MultiPolygon"):
            continue
        polygon = geom["type"] in ("Polygon", "MultiPolygon")
        for line in _iter_line_coords(geom.get("coordinates")):
            for a, b in zip(line, line[1:]):
                if polygon and (any(a[k] == b[k] and (a[k] <= 0 or a[k] >= extent) for k in (0, 1))
                                or (name == "ocean" and any(a[k] == b[k] == extent // 2 for k in (0, 1)))):
                    continue
                raw.append((*a, *b))
                gates.append(gate)
    segments = np.asarray(raw, dtype=np.float32).reshape(-1, 4)
    gates = np.asarray(gates, dtype=np.uint8)
    try:
        reference = weakref.ref(tile)
    except TypeError:
        reference = lambda: tile  # Lightweight test/provider objects.
    cache[key] = (reference, segments, gates)
    while len(cache) > 1 and (len(cache) > 256 or sum(v[1].nbytes + v[2].nbytes for v in cache.values()) > 16 * 1024 * 1024):
        cache.popitem(last=False)
    # Do not retain even a single oversized entry.
    if segments.nbytes + gates.nbytes > 16 * 1024 * 1024:
        cache.pop(key, None)
    return segments, gates


def _clip_segments(segments, width, height):
    """Batch Liang–Barsky, followed by terminal-resolution quantisation."""
    x0, y0, x1, y1 = segments.T
    dx, dy = x1 - x0, y1 - y0
    low, high = np.zeros(len(segments)), np.ones(len(segments))
    valid = np.ones(len(segments), bool)
    for p, q in ((-dx, x0), (dx, width - 1 - x0), (-dy, y0), (dy, height - 1 - y0)):
        moving = p != 0
        valid &= moving | (q >= 0)
        ratio = np.divide(q, p, out=np.zeros_like(q), where=moving)
        low = np.where(p < 0, np.maximum(low, ratio), low)
        high = np.where(p > 0, np.minimum(high, ratio), high)
    valid &= low <= high
    result = np.stack((x0 + low * dx, y0 + low * dy, x0 + high * dx, y0 + high * dy), axis=-1)
    return np.rint(result[valid]).astype(np.int32)


def draw_solid_geometry(rows, source, *, center_lat, center_lon, z, term_w, term_h,
                        canvas_px_w, canvas_px_h, style, max_fetch_zoom=14,
                        vector_only=False):
    names = ROADS | WATER | (BUILDINGS if vector_only and z >= 15 else frozenset())
    key = (center_lat, center_lon, z, term_w, term_h, canvas_px_w, canvas_px_h,
           repr(style), max_fetch_zoom, vector_only)
    cache = getattr(source, "_solid_geometry_cache", None)
    if cache is None:
        cache = source._solid_geometry_cache = OrderedDict()
    cached = cache.get(key)
    if cached is not None:
        cache.move_to_end(key)
        stamps, plan = cached
    else:
        missing = getattr(source, "overlay_missing", 0)
        fetch_z = min(z, max_fetch_zoom)
        tile_size = 256 * 2 ** (z - fetch_z)
        cx, cy = latlon_to_tile_xy(center_lat, center_lon, z)
        left, top = cx * 256 - canvas_px_w / 2, cy * 256 - canvas_px_h / 2
        sx, sy = term_w / canvas_px_w, term_h / canvas_px_h
        cells = {}
        groups = {}
        n = 2 ** fetch_z
        for tx in range(max(0, math.floor(left / tile_size)), min(n, math.floor((left + canvas_px_w) / tile_size) + 1)):
            for ty in range(max(0, math.floor(top / tile_size)), min(n, math.floor((top + canvas_px_h) / tile_size) + 1)):
                tile = source.get_overlay_tile(fetch_z, tx, ty, layer_names=names)
                if tile is None:
                    continue
                for name, layer in tile.layers.items():
                    road = name in ROADS
                    color = style.road_color if road else style.water if name in WATER else style.building
                    color = readable_color(color, style.bg, 3.0)
                    paint = "fg:#%02x%02x%02x" % tuple(color)
                    extent = layer.get("extent") or 4096
                    segments, gates = _prepared_segments(source, tile, name, layer)
                    segments = segments[gates <= z]
                    if not len(segments):
                        continue
                    offset = np.array([tx * tile_size - left, ty * tile_size - top] * 2)
                    projected = (segments * (tile_size / extent) + offset) * [sx, sy, sx, sy]
                    clipped = _clip_segments(projected, term_w, term_h)
                    if len(clipped):
                        groups.setdefault((2 if road else 1, paint), []).append(clipped)
        for (priority, paint), batches in sorted(groups.items()):
            # Identical terminal segments add no detail. Their source geometry
            # can be orders of magnitude denser than the terminal cell grid.
            segments = np.concatenate(batches)
            reverse = (segments[:, 0] > segments[:, 2]) | ((segments[:, 0] == segments[:, 2]) & (segments[:, 1] > segments[:, 3]))
            segments[reverse] = segments[reverse][:, [2, 3, 0, 1]]
            for segment in np.unique(segments, axis=0).tolist():
                diagonal = _line_cells(*segment)
                path = []
                for point in diagonal:
                    if path and path[-1][0] != point[0] and path[-1][1] != point[1]:
                        path.append((point[0], path[-1][1]))
                    path.append(point)
                for i, (x, y) in enumerate(path):
                    mask = 0
                    for j in (i - 1, i + 1):
                        if 0 <= j < len(path):
                            xx, yy = path[j]
                            mask |= 1 if xx < x else 2 if xx > x else 0
                            mask |= 4 if yy < y else 8 if yy > y else 0
                    old = cells.get((x, y))
                    if old and old[0] > priority:
                        continue
                    if old and old[0] == priority:
                        mask |= old[1]
                    cells[x, y] = (priority, mask, paint)
        glyphs = {0: "·", 1: "─", 2: "─", 3: "─", 4: "│", 8: "│", 12: "│",
                  5: "┘", 6: "└", 9: "┐", 10: "┌", 7: "┴", 11: "┬", 13: "┤", 14: "├", 15: "┼"}
        stamps = [(x, y, glyphs[mask], paint) for (x, y), (_, mask, paint) in cells.items()]
        plan = compile_stamps(stamps, term_w, term_h)
        if missing == getattr(source, "overlay_missing", 0):
            cache[key] = (stamps, plan)
            while len(cache) > 4:
                cache.popitem(last=False)
    if hasattr(rows, "apply_stamps"):
        rows.apply_stamps(plan)
    else:
        _stamp_cells_batch(rows, term_w, stamps)
    return len(stamps)


def luminance(rgb):
    a = np.asarray(rgb, dtype=np.float32) / 255
    a = np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)
    return a @ np.array([.2126, .7152, .0722], np.float32)


def readable_color(rgb, bg, minimum=3.0):
    """Move toward black/white only as far as necessary; preserve hue ordering."""
    original = np.asarray(rgb, dtype=np.float32)
    out = original.copy()
    background = luminance(bg)
    target = 0 if background > .179 else 255
    for amount in np.linspace(0, 1, 17):
        lum = luminance(out)
        ratio = (np.maximum(lum, background) + .05) / (np.minimum(lum, background) + .05)
        bad = ratio < minimum
        if not np.any(bad):
            break
        candidate = original * (1 - amount) + target * amount
        out = np.where(np.asarray(bad)[..., None], candidate, out)
    return out.clip(0, 255).astype(np.uint8)
