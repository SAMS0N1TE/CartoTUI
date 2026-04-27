"""Geodesy helpers for Web Mercator XYZ tiles.

Conversions between (lat, lon) and tile (x, y) at a given zoom level, plus a
viewport-aware degree-per-cell helper used by panning so a single pan step
moves the view by a sensible fraction of what's visible.
"""

from __future__ import annotations

import math
from typing import Tuple

__all__ = [
    "MAX_LAT",
    "TILE_SIZE",
    "clamp_lat",
    "wrap_lon",
    "latlon_to_tile_xy",
    "tile_xy_to_latlon",
    "tile_bounds",
    "viewport_deg_per_cell",
]

# Web Mercator valid latitude limit (≈ atan(sinh(π)) in degrees).
MAX_LAT = 85.05112878
TILE_SIZE = 256  # px per OSM/web mercator tile


def clamp_lat(lat: float) -> float:
    """Clamp latitude to the Web Mercator valid range."""
    return max(min(lat, MAX_LAT), -MAX_LAT)


def wrap_lon(lon: float) -> float:
    """Wrap longitude to [-180, 180)."""
    lon = ((lon + 180.0) % 360.0) - 180.0
    # Avoid -180 exact to keep integer XYZ math stable.
    return -179.999999 if lon <= -180.0 else lon


def latlon_to_tile_xy(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    """Convert lat/lon to fractional tile coordinates."""
    lat = clamp_lat(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_xy_to_latlon(x: float, y: float, zoom: int) -> Tuple[float, float]:
    """Convert (fractional) tile coordinate to (lat, lon)."""
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def tile_bounds(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    """Return (lat_min, lon_min, lat_max, lon_max) of a tile."""
    lat1, lon1 = tile_xy_to_latlon(x, y + 1, zoom)
    lat2, lon2 = tile_xy_to_latlon(x + 1, y, zoom)
    return lat1, lon1, lat2, lon2


def viewport_deg_per_cell(
    lat: float,
    zoom: int,
    cell_w_px: int = 8,
    cell_h_px: int = 16,
) -> Tuple[float, float]:
    """Return (deg_per_cell_lon, deg_per_cell_lat) at the given lat/zoom.

    Used to translate "pan by one terminal cell" into a real-world step. The
    cell pixel sizes correspond to how much of a 256 px tile a single cell
    represents; the defaults match the renderer's downsampling assumption of
    8 px wide × 16 px tall per character cell.
    """
    n = 2.0 ** zoom
    deg_per_px_lon = 360.0 / (n * TILE_SIZE)
    # Mercator y is non-linear in lat; use derivative around current lat.
    lat_rad = math.radians(clamp_lat(lat))
    deg_per_px_lat = (360.0 / (n * TILE_SIZE)) * math.cos(lat_rad)
    return deg_per_px_lon * cell_w_px, deg_per_px_lat * cell_h_px
