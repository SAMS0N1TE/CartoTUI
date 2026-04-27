"""Vector tile rasteriser.

Takes a set of decoded vector tiles (from ``vector_source.VectorTile``) and
draws them onto a Pillow ``Image`` styled for terminal display. Output is a
high-contrast, mono-friendly canvas where:

  * Water polygons become flat dark fills
  * Land/landuse polygons fill the background
  * Roads are drawn as thick antialiased lines, prioritised by class
  * Place name labels are stamped at point features

The final image is then handed to the existing renderer (ASCII / quadrant /
braille), which gives us all the existing modes for free.

This module deliberately *does not* do real Mapbox style spec compliance —
it implements just enough cartography to look like an old GPS / Magellan /
Garmin unit, which is the actual goal.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from cartotui.geodesy import latlon_to_tile_xy
from cartotui.vector_source import VectorTile, VectorTileSource

log = logging.getLogger("cartotui.raster_v")

__all__ = ["rasterise_view", "ROAD_CLASS_PRIORITY", "VectorStyle", "default_style"]


# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------


# Higher priority = drawn last (on top) and thicker.
ROAD_CLASS_PRIORITY: Dict[str, int] = {
    # Protomaps "roads" pmap:kind values (and Mapbox-style "class" values too)
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


@dataclass
class VectorStyle:
    """Drawing parameters for the rasteriser.

    Colours are RGB tuples. The rasteriser draws in *grayscale-ish* tones with
    enough range that the threshold/quantisation step has something to work
    with. The chrome theme then tints the foreground at the terminal layer.

    The defaults aim for: dark background, mid-tone water (so you can see
    coastlines), bright roads with class-graded brightness, mid-grey
    buildings. This gives 4-5 distinct tonal levels — enough for a 5-step
    palette to actually use its full range.
    """

    bg:       Tuple[int, int, int] = (15, 15, 20)      # subtle bg, not pure black
    water:    Tuple[int, int, int] = (95, 105, 120)    # mid-tone — visible
    park:     Tuple[int, int, int] = (60, 80, 60)      # darker than land, lighter than bg
    building: Tuple[int, int, int] = (75, 75, 80)
    road_color: Tuple[int, int, int] = (255, 255, 255) # always brightest
    label_color: Tuple[int, int, int] = (255, 255, 255)
    halo_color:  Tuple[int, int, int] = (0, 0, 0)

    # Road widths in pixels by priority class (clamped to >=1).
    road_widths: Dict[int, int] = None  # type: ignore[assignment]

    # Whether to draw labels at all.
    draw_labels: bool = True

    def __post_init__(self):
        if self.road_widths is None:
            self.road_widths = {
                10: 6,  # motorway
                9: 5,
                8: 4,
                7: 3,
                6: 3,
                5: 2,
                4: 2,
                3: 1,
                2: 1,
                1: 1,
            }


def default_style(theme: str = "amber") -> VectorStyle:
    """Return a sensible style preset for a theme name.

    The rasteriser draws in *grayscale* and the chrome theme applies the
    colour cast through the terminal foreground style. So even amber/green
    themes use white/gray here.
    """
    if theme == "paper":
        return VectorStyle(
            bg=(245, 240, 225),
            water=(180, 200, 220),
            park=(210, 230, 200),
            building=(220, 215, 200),
            road_color=(40, 30, 25),
            label_color=(20, 20, 20),
            halo_color=(245, 240, 225),
        )
    # Default mono-on-black for amber/green/dark/retro
    return VectorStyle()


# ---------------------------------------------------------------------------
# Rasterise
# ---------------------------------------------------------------------------


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
) -> Image.Image:
    """Render a vector-tile view into a Pillow RGB image."""

    style = style or default_style()
    width_px = max(1, int(width_px))
    height_px = max(1, int(height_px))

    # Many basemaps cap at z=15. If the user is at z=16 we still want output —
    # ask for the parent tile and scale the geometry up.
    fetch_z = min(max(z, pmap_min_zoom), pmap_max_zoom)
    scale = 2 ** (z - fetch_z)  # 1.0 if we got the requested zoom

    # Find the set of tiles that intersect the view.
    xt, yt = latlon_to_tile_xy(lat, lon, z)
    extent = 4096  # MVT default extent, used as fallback if a tile lacks it
    tile_size_px = 256.0 * scale  # px per fetched tile at our render zoom

    # Top-left tile centre in pixel space:
    cx_px = width_px / 2.0
    cy_px = height_px / 2.0

    # World-pixel offset of the canvas top-left.
    world_left_px = (xt * 256.0) - cx_px
    world_top_px = (yt * 256.0) - cy_px
    world_right_px = world_left_px + width_px
    world_bot_px = world_top_px + height_px

    # In fetch_z tile space:
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

    # Pass 1: water + landuse (filled polygons under everything)
    # Pass 2: roads, in order of class priority
    # Pass 3: labels

    tiles: List[Tuple[VectorTile, float, float, float]] = []
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            tile = source.get_tile(fetch_z, tx, ty)
            if tile is None:
                continue
            # Pixel offset where the tile's (0,0) goes on the canvas.
            tile_screen_x = tx * tile_size_px - world_left_px
            tile_screen_y = ty * tile_size_px - world_top_px
            # Per-tile px-per-extent factor.
            px_per_ext = tile_size_px / float(tile.extent or extent)
            tiles.append((tile, tile_screen_x, tile_screen_y, px_per_ext))

    # Diagnostic log: how many tiles + which layers we got. If this prints
    # zero tiles or empty layers, the source isn't returning data — that's
    # the actual cause of an "all black" vector render.
    if not tiles:
        log.info(
            "rasterise_view: 0 tiles loaded for view at z=%d (%.4f,%.4f); "
            "vector source returning None — check API key / network / source URL",
            z, lat, lon,
        )
    else:
        layer_summary = {}
        for tile, _sx, _sy, _ppe in tiles:
            for lname, layer in tile.layers.items():
                layer_summary[lname] = layer_summary.get(lname, 0) + len(
                    layer.get("features", [])
                )
        log.info(
            "rasterise_view: %d tiles, layers/features: %s",
            len(tiles),
            ", ".join(f"{k}={v}" for k, v in sorted(layer_summary.items())),
        )

    # Render passes
    _draw_water_and_landuse(draw, tiles, style)
    _draw_roads(draw, tiles, style)
    if style.draw_labels:
        _draw_labels(draw, tiles, style, width_px, height_px)

    return img


def _xform_geom(
    coords,
    sx: float,
    sy: float,
    px_per_ext: float,
):
    """Transform a single GeoJSON coords array from tile-local to canvas px.

    Recurses through the nested-list structure of GeoJSON coordinates.
    """
    if not coords:
        return coords
    first = coords[0]
    # Leaf: [x, y]
    if isinstance(first, (int, float)):
        return (sx + coords[0] * px_per_ext, sy + coords[1] * px_per_ext)
    # Else: list of (sub-)coords
    return [_xform_geom(c, sx, sy, px_per_ext) for c in coords]


def _flatten_lines(coords) -> Iterable[List[Tuple[float, float]]]:
    """Yield successive polylines from a (possibly multi-) line geometry."""
    if not coords:
        return
    first = coords[0]
    if isinstance(first, tuple) and len(first) == 2 and isinstance(first[0], (int, float)):
        yield list(coords)
        return
    if isinstance(first, list) and first and isinstance(first[0], (int, float)):
        # MultiPoint or LineString that passed through transform
        yield [tuple(p) for p in coords]
        return
    # Otherwise it's a list-of-lines.
    for sub in coords:
        yield from _flatten_lines(sub)


def _flatten_polygons(coords) -> Iterable[List[Tuple[float, float]]]:
    """Yield outer rings from polygon / multi-polygon geometry."""
    if not coords:
        return
    # Polygon: [[ring0], [ring1], ...]
    # MultiPolygon: [[[ring0],...], ...]
    first = coords[0]
    if first and isinstance(first[0], tuple):
        # It's a single ring at top? No — Polygon is rings inside list.
        yield [tuple(p) for p in first]
        return
    # MultiPolygon
    if first and isinstance(first[0], list):
        for poly in coords:
            if poly and isinstance(poly[0], (list, tuple)):
                ring = poly[0]
                if ring and isinstance(ring[0], tuple):
                    yield [tuple(p) for p in ring]


# ---------------------------------------------------------------------------
# Layer drawing
# ---------------------------------------------------------------------------


_WATER_LAYER_NAMES = {"water", "ocean", "rivers", "lakes"}
_LANDUSE_LAYER_NAMES = {"landuse", "landcover", "natural"}
_PARK_KINDS = {"park", "wood", "forest", "grass", "playground", "garden", "nature_reserve"}
_BUILDING_LAYER = "buildings"
_ROAD_LAYERS = {"roads", "transportation"}
_PLACE_LAYERS = {"places"}


def _draw_water_and_landuse(draw, tiles, style):
    for tile, sx, sy, px_per_ext in tiles:
        # Water
        for layer_name in _WATER_LAYER_NAMES:
            layer = tile.layers.get(layer_name)
            if not layer:
                continue
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=style.water)
                        except Exception:
                            pass

        # Landuse / parks
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
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=fill)
                        except Exception:
                            pass

        # Buildings
        layer = tile.layers.get(_BUILDING_LAYER)
        if layer:
            for feat in layer.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
                for ring in _flatten_polygons(xformed):
                    if len(ring) >= 3:
                        try:
                            draw.polygon(ring, fill=style.building)
                        except Exception:
                            pass


def _draw_roads(draw, tiles, style):
    # Collect (priority, sx, sy, px_per_ext, geometry) so we can sort and draw
    # higher-priority roads on top.
    items: List[Tuple[int, float, float, float, dict, dict]] = []
    for tile, sx, sy, px_per_ext in tiles:
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
                # Some Protomaps road kinds are like "highway", "minor_road".
                priority = ROAD_CLASS_PRIORITY.get(cls, 1)
                items.append((priority, sx, sy, px_per_ext, geom, props))

    items.sort(key=lambda t: t[0])

    for priority, sx, sy, px_per_ext, geom, _props in items:
        width = style.road_widths.get(priority, 1)
        xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
        for line in _flatten_lines(xformed):
            if len(line) < 2:
                continue
            try:
                draw.line(line, fill=style.road_color, width=width, joint="curve")
            except Exception:
                # joint not supported on older Pillow → draw without it
                try:
                    draw.line(line, fill=style.road_color, width=width)
                except Exception:
                    pass


def _draw_labels(draw, tiles, style, w: int, h: int):
    # Collect candidate labels with their priority and position.
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
                # Priority — bigger places first.
                kind = (props.get("class") or props.get("kind") or
                        props.get("pmap:kind") or "").lower()
                rank_map = {"country": 0, "state": 1, "city": 2, "town": 3,
                            "village": 4, "suburb": 5, "neighbourhood": 6,
                            "neighborhood": 6, "locality": 7, "hamlet": 8}
                rank = rank_map.get(kind, 9)
                # Per-feature rank attribute (Protomaps "pmap:min_zoom"-like)
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

    # Simple collision avoidance: track placed bounding boxes, skip any new
    # label that overlaps an existing one.
    placed: List[Tuple[float, float, float, float]] = []
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    char_w, char_h = 6, 11  # rough default-font cell

    def overlaps(box, others):
        x0, y0, x1, y1 = box
        for ox0, oy0, ox1, oy1 in others:
            if not (x1 < ox0 or x0 > ox1 or y1 < oy0 or y0 > oy1):
                return True
        return False

    for _rank, px, py, name in candidates[:200]:  # cap to avoid runaway
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
        # Halo first — draw text 8 times offset by 1 pixel for a thick outline,
        # then text on top in label colour.
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
