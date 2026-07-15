
from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter

from cartotui.cache import TileCache
from cartotui.geodesy import TILE_SIZE, latlon_to_tile_xy

log = logging.getLogger("cartotui.composite")

__all__ = ["composite_from_tiles", "tiles_for_view", "apply_image_adjustments"]

_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

_KNEE = 0.7


def _shoulder(v: np.ndarray, knee: float = _KNEE) -> np.ndarray:
    """Compress everything above `knee` into [knee, 1) along a tanh asymptote.

    A plain multiply clips: on a light theme it pins whole regions to pure white
    and the hue with it. This bends instead, so brightening keeps highlights
    apart from each other however hard it is pushed.
    """
    head = max(1.0 - knee, 1e-6)
    return np.where(v > knee, knee + head * np.tanh((v - knee) / head), v)


def _soft_clip01(v: np.ndarray, knee: float = _KNEE) -> np.ndarray:
    """`_shoulder` at both ends -- contrast pushes values past 0 as well as 1."""
    v = _shoulder(v, knee)
    v = 1.0 - _shoulder(1.0 - v, knee)
    return np.clip(v, 0.0, 1.0)


def _retint(rgb: np.ndarray, lum0: np.ndarray, lum1: np.ndarray) -> np.ndarray:
    """Move pixels from luminance `lum0` to `lum1`, keeping their colour.

    Scaling RGB by the luminance ratio holds the channel proportions -- hence
    the hue and saturation -- fixed. Where that overshoots the gamut, the pixel
    is pulled toward its own grey just far enough to fit, which reads as a
    highlight rolling off rather than a channel slamming into its ceiling.

    A black pixel has no colour to scale, so the ratio cannot move it; it is
    assigned its target grey outright, which is what lets a raised black point
    lift a theme with a #000000 background.

    The peak is taken with pairwise maxima over contiguous channel slices rather
    than max(axis=-1): reducing a 3-long trailing axis is strided and costs an
    order of magnitude more, enough to dominate the whole frame.
    """
    ratio = lum1 / np.maximum(lum0, 1e-5)
    out = rgb * ratio[..., None]

    black = lum0 < 1e-4
    if black.any():
        out[black] = lum1[black][:, None]

    peak = np.maximum(np.maximum(out[..., 0], out[..., 1]), out[..., 2])

    over = peak > 1.0
    if over.any():
        l1 = lum1[over][:, None]
        hit = out[over]
        room = np.maximum(peak[over][:, None] - l1, 1e-5)
        t = np.clip((1.0 - l1) / room, 0.0, 1.0)
        out[over] = l1 + (hit - l1) * t

    return np.clip(out, 0.0, 1.0, out=out)


def _luma_curve(
    *,
    brightness: float,
    contrast: float,
    gamma: float,
    black_point: float,
    white_point: float,
    pivot: float,
) -> np.ndarray:
    """The whole tone chain as a 256-entry luminance transfer curve.

    Every knob is a function of luminance alone, so they compose into one curve
    that can be sampled per pixel. That keeps the expensive parts (tanh, pow)
    off the image and lets a frame cost one lookup instead of four passes.
    """
    y = np.linspace(0.0, 1.0, 256, dtype=np.float32)

    if abs(brightness - 1.0) > 1e-3:
        y = _shoulder(y * max(0.0, brightness))
    if abs(contrast - 1.0) > 1e-3:
        y = _soft_clip01(pivot + (y - pivot) * max(0.0, contrast))
    if abs(gamma - 1.0) > 1e-3:
        y = np.power(np.clip(y, 0.0, 1.0), 1.0 / max(1e-3, gamma), dtype=np.float32)

    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, 0.05, 1.0))
    if bp > wp:
        bp, wp = wp, bp
    if bp > 1e-3 or wp < 1.0 - 1e-3:
        y = bp + np.clip(y, 0.0, 1.0) * (wp - bp)

    return np.clip(y, 0.0, 1.0).astype(np.float32)


def _tone(
    img: Image.Image,
    *,
    brightness: float,
    contrast: float,
    gamma: float,
    saturation: float,
    black_point: float,
    white_point: float,
) -> Image.Image:
    """Exposure -> contrast -> gamma -> output levels -> saturation.

    The tone knobs all act on luminance and land in a single re-tint, so colour
    survives: nothing is blended toward a flat grey, and pulling contrast down
    flattens tone without draining chroma the way the old enhancer did.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    rgb = np.asarray(img, dtype=np.float32) / 255.0
    lum = rgb @ _LUMA

    curve = _luma_curve(
        brightness=brightness, contrast=contrast, gamma=gamma,
        black_point=black_point, white_point=white_point,
        pivot=float(lum.mean()),
    )
    target = curve[np.clip(lum * 255.0 + 0.5, 0, 255).astype(np.uint8)]
    rgb = _retint(rgb, lum, target)

    if abs(saturation - 1.0) > 1e-3:
        grey = target[..., None]
        rgb = np.clip(grey + (rgb - grey) * max(0.0, saturation), 0.0, 1.0)

    return Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")


def apply_image_adjustments(
    img: Image.Image,
    *,
    contrast: float = 1.0,
    brightness: float = 1.0,
    gamma: float = 1.0,
    saturation: float = 1.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
    sharpen_percent: int = 0,
    sharpen_radius: float = 1.5,
    sharpen_threshold: int = 3,
    edge_boost: bool = False,
    invert: bool = False,
) -> Image.Image:
    """Apply the tone knobs, then sharpen/edge/invert, in a fixed order."""
    if (abs(brightness - 1.0) > 1e-3 or abs(contrast - 1.0) > 1e-3
            or abs(gamma - 1.0) > 1e-3 or abs(saturation - 1.0) > 1e-3
            or black_point > 1e-3 or white_point < 1.0 - 1e-3):
        try:
            img = _tone(
                img, brightness=brightness, contrast=contrast, gamma=gamma,
                saturation=saturation, black_point=black_point,
                white_point=white_point,
            )
        except Exception as e:
            log.debug("tone adjust failed: %s", e)
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
    saturation: float = 1.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
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
        saturation=saturation,
        black_point=black_point,
        white_point=white_point,
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
