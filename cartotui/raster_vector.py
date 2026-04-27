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

# Set of (kind, ...) signatures we've already warned about. Keeps the
# "no tiles" warning from firing on every render frame when the source is
# misconfigured. Cleared implicitly when the process restarts.
_LOG_DEDUPE: set = set()

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

    Per-class road colors are supported via ``road_colors``: a dict mapping
    priority (1..10) to RGB. When a road's class isn't in the dict, the
    drawer falls back to ``road_color``. This is what gives motorways
    visual weight different from residentials at the same zoom.
    """

    bg:       Tuple[int, int, int] = (15, 15, 20)      # subtle bg, not pure black
    water:    Tuple[int, int, int] = (95, 105, 120)    # mid-tone — visible
    park:     Tuple[int, int, int] = (60, 80, 60)      # darker than land, lighter than bg
    building: Tuple[int, int, int] = (75, 75, 80)
    road_color: Tuple[int, int, int] = (255, 255, 255) # fallback / single-color
    label_color: Tuple[int, int, int] = (255, 255, 255)
    halo_color:  Tuple[int, int, int] = (0, 0, 0)

    # Aircraft overlay colours
    aircraft_color:          Tuple[int, int, int] = (255, 200, 60)
    aircraft_selected_color: Tuple[int, int, int] = (255, 255, 255)
    aircraft_emergency_color: Tuple[int, int, int] = (255, 80, 80)
    aircraft_label_color:    Tuple[int, int, int] = (255, 220, 120)
    aircraft_halo_color:     Tuple[int, int, int] = (0, 0, 0)

    # Road widths in pixels by priority class (clamped to >=1).
    road_widths: Dict[int, int] = None  # type: ignore[assignment]
    # Per-class road colors. When a key is missing we fall back to road_color.
    road_colors: Dict[int, Tuple[int, int, int]] = None  # type: ignore[assignment]

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
        if self.road_colors is None:
            # Default palette is a brightness ramp keyed on priority. Values
            # tuned so the threshold pass keeps even the lowest-priority
            # roads visible against the bg, while motorways punch hard.
            self.road_colors = {
                10: (255, 255, 255),  # motorway — brightest
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
        """Return the road color for a class priority, with fallback."""
        return self.road_colors.get(priority, self.road_color)


def default_style(theme: str = "amber") -> VectorStyle:
    """Return a sensible style preset for a theme name.

    The rasteriser draws in *grayscale* and the chrome theme applies the
    colour cast through the terminal foreground style. So even amber/green
    themes use white/gray here — the actual colour comes from the theme
    style class. The road brightness ramp is what creates the visual road
    hierarchy *before* the theme tint hits.

    User config can override any field via ``theme.road_colors`` etc;
    that's wired in ``themes.theme_vector_style``.
    """
    if theme == "paper":
        # Light theme — invert the road ramp so dark = important.
        return VectorStyle(
            bg=(245, 240, 225),
            water=(180, 200, 220),
            park=(210, 230, 200),
            building=(220, 215, 200),
            road_color=(40, 30, 25),
            label_color=(20, 20, 20),
            halo_color=(245, 240, 225),
            aircraft_color=(180, 60, 30),
            aircraft_selected_color=(0, 0, 0),
            aircraft_emergency_color=(220, 0, 0),
            aircraft_label_color=(50, 30, 20),
            aircraft_halo_color=(245, 240, 225),
            road_colors={
                10: (20, 15, 10),
                9:  (35, 30, 25),
                8:  (50, 45, 40),
                7:  (65, 60, 55),
                6:  (80, 75, 70),
                5:  (95, 90, 85),
                4:  (110, 105, 100),
                3:  (125, 120, 115),
                2:  (140, 135, 130),
                1:  (155, 150, 145),
            },
        )
    if theme == "light":
        return VectorStyle(
            bg=(240, 240, 240),
            water=(170, 195, 220),
            park=(200, 225, 195),
            building=(215, 215, 215),
            road_color=(50, 50, 50),
            label_color=(30, 30, 30),
            halo_color=(240, 240, 240),
            aircraft_color=(0, 50, 150),
            aircraft_selected_color=(0, 0, 0),
            aircraft_emergency_color=(200, 0, 0),
            aircraft_label_color=(0, 50, 150),
            aircraft_halo_color=(240, 240, 240),
            road_colors={
                10: (30, 30, 30), 9: (45, 45, 45), 8: (60, 60, 60),
                7:  (75, 75, 75), 6: (90, 90, 90), 5: (105, 105, 105),
                4: (120, 120, 120), 3: (135, 135, 135),
                2: (150, 150, 150), 1: (165, 165, 165),
            },
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
    aircraft_overlay: Optional[Iterable] = None,
    selected_icao: Optional[str] = None,
) -> Image.Image:
    """Render a vector-tile view into a Pillow RGB image.

    ``aircraft_overlay`` is an iterable of ``cartotui.traffic.Aircraft``
    instances to plot on top of the basemap. Items lacking a position
    (``has_position()`` is False) are skipped silently. ``selected_icao``
    if given draws the matching aircraft in the selected colour with a
    halo so the user can tell which one is highlighted in the sidebar.
    """

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

    # Diagnostic log. This used to fire every render at INFO level and bled
    # into the live terminal under prompt_toolkit's alt-screen. Now:
    #   - "no tiles" once per (z, lat-rounded, lon-rounded) at WARNING
    #     because that case is genuinely actionable.
    #   - the per-render success summary at DEBUG so it stays out of the
    #     default log file and the terminal alike.
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

    # Render passes
    _draw_water_and_landuse(draw, tiles, style)
    _draw_roads(draw, tiles, style)
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
        color = style.color_for_priority(priority)
        xformed = _xform_geom(geom["coordinates"], sx, sy, px_per_ext)
        for line in _flatten_lines(xformed):
            if len(line) < 2:
                continue
            try:
                draw.line(line, fill=color, width=width, joint="curve")
            except Exception:
                # joint not supported on older Pillow → draw without it
                try:
                    draw.line(line, fill=color, width=width)
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


# ---------------------------------------------------------------------------
# Aircraft overlay
# ---------------------------------------------------------------------------

# Per-aircraft hit boxes, set on each render. Format: (icao, x0, y0, x1, y1)
# in canvas pixel coordinates. The map_control reads this via
# ``last_aircraft_hitboxes`` to convert mouse clicks to ICAO selects.
_LAST_HITBOXES: List[Tuple[str, float, float, float, float]] = []


def last_aircraft_hitboxes() -> List[Tuple[str, float, float, float, float]]:
    """Return a copy of the hitboxes from the last ``rasterise_view`` call.

    Pixel-space rectangles. The caller (mouse handler) divides by the
    cell-pixel scale to convert to screen cells.
    """
    return list(_LAST_HITBOXES)


def _aircraft_canvas_xy(
    lat: float, lon: float, z: int,
    world_left_px: float, world_top_px: float,
) -> Tuple[float, float]:
    """Project lat/lon to canvas pixel coords using the same Web Mercator
    convention as the tile layer. Out-of-range values are simply allowed
    to land off-canvas; the caller filters.
    """
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
    """Draw a triangular aircraft marker at (cx, cy), pointing at track_deg.

    Track is degrees true (0 = north, 90 = east). If unknown, draw a circle.
    """
    if track_deg is None:
        r = size
        try:
            draw.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=halo)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        except Exception:
            pass
        return

    # Triangle vertices in marker-local coords: nose forward (+y in our
    # convention before rotation), two tail corners.
    a = math.radians(track_deg)
    sin_a, cos_a = math.sin(a), math.cos(a)
    pts = [(0.0, -size * 1.4), (size * 0.9, size * 0.8), (-size * 0.9, size * 0.8)]

    def rot(p):
        x, y = p
        # Standard 2D rotation: positive a rotates the +y axis (which we
        # treat as "nose") clockwise toward east, matching compass bearing.
        rx = x * cos_a - y * sin_a
        ry = x * sin_a + y * cos_a
        return (cx + rx, cy + ry)

    poly = [rot(p) for p in pts]
    try:
        # Halo
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
    """Plot aircraft on top of the basemap.

    Aircraft outside the viewport (with a small margin so half-on-edge
    icons aren't clipped) are skipped. The selected aircraft is drawn
    last so its glyph and label paint over its neighbours.
    """
    global _LAST_HITBOXES
    _LAST_HITBOXES = []

    # Use the existing label font for callsign labels.
    font = None
    try:
        font = ImageFont.load_default()
    except Exception:
        pass

    # Marker size scales modestly with zoom — bigger markers at higher zoom
    # so the icons don't disappear when you're zoomed in close. Capped on
    # both ends so they're never tiny or absurd.
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
        items.append(selected_item)  # draw selected last (on top)

    for ac, cx, cy, color, is_selected in items:
        # Marker
        size = marker_size + (2 if is_selected else 0)
        _aircraft_marker(
            draw, cx, cy, ac.track_deg, color, style.aircraft_halo_color, size,
        )

        # Label — short callsign next to the marker, with halo for legibility.
        if font is not None and (is_selected or marker_size >= 6):
            label = ac.display_label()
            if label:
                lx = cx + size + 2
                ly = cy - size
                # Halo
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

        # Hitbox (always recorded — used by mouse handler)
        hb = (size + 2) * 1.5
        _LAST_HITBOXES.append(
            (ac.icao, cx - hb, cy - hb, cx + hb, cy + hb)
        )
