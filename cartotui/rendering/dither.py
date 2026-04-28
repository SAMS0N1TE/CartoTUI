"""Dithering algorithms for the renderer.

All functions take a normalised float32 luminance array in [0, 1] and a number
of palette levels (i.e. number of glyphs in the palette) and return an int
array of palette indices.

`bayer` is fully vectorised. `atkinson` and `floyd` are inherently serial so
they're written as plain Python loops over a NumPy buffer; they're fast enough
for terminal-sized images (~120×40 cells) and the visual benefit is real.
"""

from __future__ import annotations

import numpy as np

__all__ = ["quantize_no_dither", "bayer", "atkinson", "floyd_steinberg"]


# 4×4 ordered dither matrix, scaled to [0, 1] with an offset of -0.5.
_BAYER4 = np.array(
    [
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5],
    ],
    dtype=np.float32,
) / 16.0 - 0.5


def quantize_no_dither(lum: np.ndarray, levels: int) -> np.ndarray:
    levels = max(2, levels)
    return np.clip(np.round(lum * (levels - 1)).astype(np.int32), 0, levels - 1)


def bayer(lum: np.ndarray, levels: int, strength: float = 1.0) -> np.ndarray:
    """4×4 ordered dither — fast, repeatable, slightly hatched look."""
    levels = max(2, levels)
    h, w = lum.shape
    tile = np.tile(_BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]
    nudged = lum + tile * (strength / (levels - 1))
    return np.clip(np.round(nudged * (levels - 1)).astype(np.int32), 0, levels - 1)


def atkinson(lum: np.ndarray, levels: int) -> np.ndarray:
    """Atkinson dithering — distributes 6/8 of the error to 6 neighbours."""
    levels = max(2, levels)
    buf = lum.astype(np.float32, copy=True)
    h, w = buf.shape
    # Precompute step in normalised units.
    for y in range(h):
        for x in range(w):
            old = buf[y, x]
            new = round(old * (levels - 1)) / (levels - 1)
            err = (old - new) / 8.0
            buf[y, x] = new
            if x + 1 < w:
                buf[y, x + 1] += err
            if x + 2 < w:
                buf[y, x + 2] += err
            if y + 1 < h:
                if x - 1 >= 0:
                    buf[y + 1, x - 1] += err
                buf[y + 1, x] += err
                if x + 1 < w:
                    buf[y + 1, x + 1] += err
            if y + 2 < h:
                buf[y + 2, x] += err
    return np.clip(np.round(buf * (levels - 1)).astype(np.int32), 0, levels - 1)


def floyd_steinberg(lum: np.ndarray, levels: int) -> np.ndarray:
    """Classic Floyd–Steinberg — 7/16, 3/16, 5/16, 1/16 error diffusion."""
    levels = max(2, levels)
    buf = lum.astype(np.float32, copy=True)
    h, w = buf.shape
    for y in range(h):
        for x in range(w):
            old = buf[y, x]
            new = round(old * (levels - 1)) / (levels - 1)
            err = old - new
            buf[y, x] = new
            if x + 1 < w:
                buf[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x - 1 >= 0:
                    buf[y + 1, x - 1] += err * 3 / 16
                buf[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    buf[y + 1, x + 1] += err * 1 / 16
    return np.clip(np.round(buf * (levels - 1)).astype(np.int32), 0, levels - 1)
