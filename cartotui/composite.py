
from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from typing import List, Tuple

from PIL import Image, ImageEnhance, ImageFilter

from cartotui.cache import TileCache
from cartotui.geodesy import TILE_SIZE, latlon_to_tile_xy

log = logging.getLogger("cartotui.composite")

__all__ = ["composite_from_tiles", "tiles_for_view", "apply_image_adjustments"]


def apply_image_adjustments(
    img: Image.Image,
    *,
    contrast: float = 1.0,
    brightness: float = 1.0,
    gamma: float = 1.0,
    sharpen_percent: int = 0,
    sharpen_radius: float = 1.5,
    sharpen_threshold: int = 3,
    edge_boost: bool = False,
    invert: bool = False,
) -> Image.Image:
    """Apply brightness/contrast/gamma/sharpen/edge/invert in a fixed order."""
    if abs(brightness - 1.0) > 1e-3:
        try:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        except Exception as e:
            log.debug("brightness failed: %s", e)
    if abs(contrast - 1.0) > 1e-3:
        try:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        except Exception as e:
            log.debug("contrast failed: %s", e)
    if abs(gamma - 1.0) > 1e-3:
        try:
            inv = 1.0 / max(1e-3, gamma)
            lut = [min(255, max(0, int(((i / 255.0) ** inv) * 255))) for i in range(256)]
            img = img.point(lut * 3)
        except Exception as e:
            log.debug("gamma failed: %s", e)
    if edge_boost:
        try:
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        except Exception as e:
            log.debug("edge boost failed: %s", e)
    if sharpen_percent > 0:
        try:
            img = img.filter(
                ImageFilter.UnsharpMask(
                    radius=sharpen_radius,
                    percent=sharpen_percent,
                    threshold=sharpen_threshold,
                )
            )
        except Exception as e:
            log.debug("sharpen failed: %s", e)
    if invert:
        try:
            img = img.point([255 - i for i in range(256)] * 3)
        except Exception as e:
            log.debug("invert failed: %s", e)
    return img

def tiles_for_view(
    lat: float,
    lon: float,
    z: int,
    width_px: int,
    height_px: int,
    margin_tiles: int = 1,
) -> Tuple[List[Tuple[int, int, int]], int, int, float, float]:
    xt, yt = latlon_to_tile_xy(lat, lon, z)
    tx, ty = int(xt), int(yt)
    n = 2 ** z

    tiles_x = math.ceil(width_px / TILE_SIZE) + 2 * margin_tiles
    tiles_y = math.ceil(height_px / TILE_SIZE) + 2 * margin_tiles
    start_x = tx - tiles_x // 2
    start_y = ty - tiles_y // 2

    out: List[Tuple[int, int, int]] = []
    for dy in range(tiles_y):
        y = start_y + dy
        if not (0 <= y < n):
            continue
        for dx in range(tiles_x):
            x = (start_x + dx) % n
            out.append((z, x, y))
    return out, start_x, start_y, xt, yt

def composite_from_tiles(
    cache: TileCache,
    lat: float,
    lon: float,
    z: int,
    width_px: int,
    height_px: int,
    overzoom_levels: int = 2,
    contrast: float = 1.0,
    brightness: float = 1.0,
    gamma: float = 1.0,
    sharpen_percent: int = 150,
    sharpen_radius: float = 1.5,
    sharpen_threshold: int = 3,
    edge_boost: bool = False,
    invert: bool = False,
    cached_only: bool = False,
) -> Image.Image:
    width_px = max(1, int(width_px))
    height_px = max(1, int(height_px))

    tiles, start_x, start_y, xt, yt = tiles_for_view(lat, lon, z, width_px, height_px)
    n = 2 ** z

    tiles_x = math.ceil(width_px / TILE_SIZE) + 2
    tiles_y = math.ceil(height_px / TILE_SIZE) + 2
    base = Image.new("RGB", (tiles_x * TILE_SIZE, tiles_y * TILE_SIZE), (24, 26, 32))

    for z_t, x_t, y_t in tiles:
        img = cache.get_tile_with_overzoom(z_t, x_t, y_t, overzoom_levels, cached_only=cached_only)
        if img is None:
            continue
        dy = y_t - start_y
        for dx in range(tiles_x):
            if (start_x + dx) % n == x_t:
                base.paste(img, (dx * TILE_SIZE, dy * TILE_SIZE))
                break

    cx = (xt - start_x) * TILE_SIZE
    cy = (yt - start_y) * TILE_SIZE
    left = int(round(cx - width_px / 2))
    top = int(round(cy - height_px / 2))
    img = base.crop((left, top, left + width_px, top + height_px))

    return apply_image_adjustments(
        img,
        contrast=contrast,
        brightness=brightness,
        gamma=gamma,
        sharpen_percent=sharpen_percent,
        sharpen_radius=sharpen_radius,
        sharpen_threshold=sharpen_threshold,
        edge_boost=edge_boost,
        invert=invert,
    )

def prefetch_ring(
    cache: TileCache,
    lat: float,
    lon: float,
    z: int,
    width_px: int,
    height_px: int,
    ring_radius: int = 1,
) -> Iterable[Tuple[int, int, int]]:
    visible, start_x, start_y, _xt, _yt = tiles_for_view(lat, lon, z, width_px, height_px)
    visible_set = set(visible)
    n = 2 ** z

    tiles_x = math.ceil(width_px / TILE_SIZE) + 2
    tiles_y = math.ceil(height_px / TILE_SIZE) + 2

    for dy in range(-ring_radius, tiles_y + ring_radius):
        y = start_y + dy
        if not (0 <= y < n):
            continue
        for dx in range(-ring_radius, tiles_x + ring_radius):
            x = (start_x + dx) % n
            tile = (z, x, y)
            if tile in visible_set:
                continue
            yield tile
