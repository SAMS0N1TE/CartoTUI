
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

MAX_LAT = 85.05112878
TILE_SIZE = 256

def clamp_lat(lat: float) -> float:
    return max(min(lat, MAX_LAT), -MAX_LAT)

def wrap_lon(lon: float) -> float:
    lon = ((lon + 180.0) % 360.0) - 180.0
    return -179.999999 if lon <= -180.0 else lon

def latlon_to_tile_xy(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    lat = clamp_lat(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y

def tile_xy_to_latlon(x: float, y: float, zoom: int) -> Tuple[float, float]:
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon

def tile_bounds(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    lat1, lon1 = tile_xy_to_latlon(x, y + 1, zoom)
    lat2, lon2 = tile_xy_to_latlon(x + 1, y, zoom)
    return lat1, lon1, lat2, lon2

def viewport_deg_per_cell(
    lat: float,
    zoom: int,
    cell_w_px: int = 8,
    cell_h_px: int = 16,
) -> Tuple[float, float]:
    n = 2.0 ** zoom
    deg_per_px_lon = 360.0 / (n * TILE_SIZE)
    lat_rad = math.radians(clamp_lat(lat))
    deg_per_px_lat = (360.0 / (n * TILE_SIZE)) * math.cos(lat_rad)
    return deg_per_px_lon * cell_w_px, deg_per_px_lat * cell_h_px
