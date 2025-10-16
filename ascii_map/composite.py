#!/usr/bin/env python3
# ascii_map/composite.py
"""
Tile compositing engine for ASCII Map.

Responsible for assembling multiple map tiles into a single RGB image centered
at a target lat/lon and zoom level.

Integrates with geodesy.latlon_to_tile_xy and cache.TileCache.
Handles missing tiles, overzoom, and optional clamping of output dimensions.
"""

from __future__ import annotations
import math, threading
from typing import Optional
from PIL import Image, ImageEnhance, ImageFilter

from ascii_map.geodesy import latlon_to_tile_xy
from ascii_map.cache import TileCache

__all__ = ["composite_from_tiles"]

_lock = threading.Lock()

def composite_from_tiles(
    cache: TileCache,
    lat: float,
    lon: float,
    z: int,
    width_px: int,
    height_px: int,
    overzoom_levels: int = 2,
    contrast: float = 1.0,
    sharpen_percent: int = 200,
    sharpen_radius: float = 2.0,
    sharpen_threshold: int = 3,
    edge_boost: bool = False,
    invert: bool = False,
) -> Image.Image:
    """
    Assemble a composite image from tiles centered on (lat, lon).

    width_px, height_px define output pixel dimensions.
    Returns an RGB Pillow Image.
    """

    # --- Compute tile coordinates ---
    xt, yt = latlon_to_tile_xy(lat, lon, z)
    tx, ty = int(xt), int(yt)
    n = 2 ** z

    # --- Determine how many tiles to cover ---
    # Each tile is 256x256 px in Web Mercator.
    tile_size = 256
    tiles_x = math.ceil(width_px / tile_size) + 2
    tiles_y = math.ceil(height_px / tile_size) + 2

    # --- Composite buffer ---
    total_w = tiles_x * tile_size
    total_h = tiles_y * tile_size
    base = Image.new("RGB", (total_w, total_h), (0, 0, 0))

    # --- Top-left tile indices ---
    start_x = tx - tiles_x // 2
    start_y = ty - tiles_y // 2

    # --- Fetch and paste tiles ---
    for dy in range(tiles_y):
        for dx in range(tiles_x):
            x = (start_x + dx) % n
            y = start_y + dy
            if not (0 <= y < n):
                continue
            img = cache.get_tile_with_overzoom(z, x, y, overzoom_levels)
            if img:
                base.paste(img, (dx * tile_size, dy * tile_size))

    # --- Crop to center view ---
    cx = (xt - tx + 0.5) * tile_size
    cy = (yt - ty + 0.5) * tile_size
    left = int(cx - width_px / 2)
    top = int(cy - height_px / 2)
    right = left + width_px
    bottom = top + height_px
    cropped = base.crop((left, top, right, bottom))

    # --- Post-process ---
    img = cropped

    if contrast != 1.0:
        try:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        except Exception:
            pass

    if edge_boost:
        try:
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        except Exception:
            pass

    if sharpen_percent != 100:
        try:
            # Pillow unsharp mask uses percent, radius, threshold
            img = img.filter(ImageFilter.UnsharpMask(radius=sharpen_radius,
                                                     percent=sharpen_percent,
                                                     threshold=sharpen_threshold))
        except Exception:
            pass

    if invert:
        try:
            lut = [255 - i for i in range(256)]
            img = img.point(lut * 3)
        except Exception:
            pass

    return img
