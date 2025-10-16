#!/usr/bin/env python3
# ascii_map/geodesy.py
"""
Geodesy utilities for ASCII Map.
Handles conversions between latitude/longitude and Web Mercator XYZ tile indices.
"""

import math
from typing import Tuple

__all__ = [
    "latlon_to_tile_xy",
    "tile_xy_to_latlon",
    "clamp_lat",
    "tile_bounds",
]

# Web Mercator valid latitude limit
MAX_LAT = 85.05112878


def clamp_lat(lat: float) -> float:
    """Clamp latitude to Web Mercator valid range."""
    return max(min(lat, MAX_LAT), -MAX_LAT)


def latlon_to_tile_xy(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    """
    Convert lat/lon to fractional tile coordinates at a given zoom.
    Returns (x, y) tile coordinate floats.
    """
    lat = clamp_lat(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_xy_to_latlon(x: float, y: float, zoom: int) -> Tuple[float, float]:
    """
    Convert tile coordinate to latitude/longitude (tile center).
    Returns (lat, lon).
    """
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def tile_bounds(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    """
    Return bounding box (lat_min, lon_min, lat_max, lon_max) of a tile.
    """
    lat1, lon1 = tile_xy_to_latlon(x, y + 1, zoom)
    lat2, lon2 = tile_xy_to_latlon(x + 1, y, zoom)
    return lat1, lon1, lat2, lon2
