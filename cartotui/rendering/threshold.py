"""Threshold and subpixel-fill helpers for the renderer.

This module turns a luminance image (``[0, 1]``) into per-pixel *fill
levels* in ``[0, levels-1]``. A fill level is what the backends paint:
``0`` = empty cell, ``levels-1`` = full fill. The backends pick a glyph
from their palette by fill level.

# v1.0.3 (this rewrite) — why and what changed

The previous pipeline had grown into a stack of fixes layered on top of
each other (percentile stretch, then orientation flip, then per-tile
uniform fallback, then a hard ``signal**2.0`` gamma). Each "fix" was
papering over a regression introduced by the previous one and the
default look kept getting darker.

This rewrite is a single, predictable pipeline that all four user-
facing modes route through:

    luminance ─► oriented signal ─► (optional) local stretch
              ─► black/white-point clip ─► tone curve ─► fill levels

The four user-facing modes — ``adaptive``, ``percentile``, ``edge``,
``fixed`` — are now *parameter presets* over the same code path, not
separate branches with bespoke gamma logic.

# v1.0.3a — reduced default gamma from 1.4 to 1.2

After looking at real renders, 1.4 was still over-darkening land tones
relative to road features. The default is now 1.2, which keeps mid-
tones soft (signal 0.5 → fill ~0.41 of full range) while leaving
sharp features at near-full fill (signal 0.9 → ~0.88). The user can
push it back toward 2.0 with the ``signal_gamma`` knob if they liked
the old darker look.

# Brightness/contrast interaction

The renderer applies user brightness/contrast (``[`` ``]`` ``{`` ``}``
keys) to the *image* before luminance is computed, so the threshold
sees an already-adjusted input. If the user wants darker, they press
``{``. The threshold is no longer trying to second-guess overall
image density — that knob is the user's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "compute_fill_levels",
    "compute_binary_fill",
    "estimate_orientation",
]


# ---------------------------------------------------------------------------
# Mode presets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ModeParams:
    """Per-mode tunables. Modes are presets over this struct."""

    use_local_stretch: bool
    black_pct: float
    white_pct: float
    is_edge: bool


def _params_for(mode: str) -> _ModeParams:
    if mode == "adaptive":
        return _ModeParams(True,  8.0,  96.0, False)
    if mode == "edge":
        return _ModeParams(False, 5.0,  95.0, True)
    if mode == "fixed":
        # No stretching at all. The orient flip still happens so that
        # "feature" pixels are the high end of the signal; quantising
        # straight against [0, 1] gives a predictable, monotone mapping.
        return _ModeParams(False, 0.0, 100.0, False)
    # "percentile" + anything we don't recognise
    return _ModeParams(False, 8.0, 96.0, False)


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


def estimate_orientation(lum: np.ndarray) -> str:
    """Return ``"dark"`` (features bright on dark bg, e.g. vector mode)
    or ``"bright"`` (features dark on bright bg, e.g. OSM raster).

    The 0.4 cutoff was chosen empirically — most real tiles either sit
    well below 0.3 (dark vector renders) or well above 0.6 (cream
    raster), so the threshold rarely flips on incidental brightness
    shifts.
    """
    return "dark" if float(lum.mean()) < 0.4 else "bright"


def _orient_signal(lum: np.ndarray) -> np.ndarray:
    """Flip the luminance map so high values always mean 'feature'.

    The single place orientation gets decided. Everything downstream
    operates on a uniform "more = more feature" convention.
    """
    if estimate_orientation(lum) == "dark":
        return lum.astype(np.float32, copy=False)
    return (1.0 - lum).astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# Stretch primitives
# ---------------------------------------------------------------------------


def _global_stretch(signal: np.ndarray, black_pct: float, white_pct: float) -> np.ndarray:
    """Robust contrast stretch by black/white percentile clipping.

    Picks the ``black_pct`` and ``white_pct`` percentiles, treats those
    as the new 0 and 1, linearly maps between them and clips outside.
    For ``black_pct=0, white_pct=100`` this is the identity (used by
    ``fixed`` mode to bypass stretching).
    """
    if black_pct <= 0.0 and white_pct >= 100.0:
        return np.clip(signal, 0.0, 1.0)
    lo = float(np.percentile(signal, black_pct))
    hi = float(np.percentile(signal, white_pct))
    if hi - lo < 1e-3:
        # Degenerate — flat tile. Leave as-is rather than dividing by ~0
        # and amplifying noise into a uniform fog.
        return np.clip(signal, 0.0, 1.0)
    out = (signal - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def _adaptive_local_stretch(
    signal: np.ndarray,
    tile_grid: int,
    black_pct: float,
    white_pct: float,
    uniform_floor: float,
) -> np.ndarray:
    """Per-tile percentile stretch with bilinear blending.

    Builds a tile_grid x tile_grid grid of (lo, hi) percentile pairs.
    For each pixel, looks up the four surrounding tile centres, computes
    the stretched signal under each tile's (lo, hi), and bilinearly
    blends. Tiles whose dynamic range is below ``uniform_floor`` pass
    through unstretched — open water and dense canopy don't get their
    sensor noise amplified into speckle.

    Returns a same-shape float32 array in [0, 1].
    """
    H, W = signal.shape
    g = max(2, int(tile_grid))

    ys = np.linspace(0, H, g + 1, dtype=int)
    xs = np.linspace(0, W, g + 1, dtype=int)
    cy = (ys[:-1] + ys[1:]) * 0.5
    cx = (xs[:-1] + xs[1:]) * 0.5

    tile_lo = np.zeros((g, g), dtype=np.float32)
    tile_hi = np.ones((g, g), dtype=np.float32)
    tile_uniform = np.zeros((g, g), dtype=bool)

    for ti in range(g):
        for tj in range(g):
            block = signal[ys[ti]:ys[ti + 1], xs[tj]:xs[tj + 1]]
            if block.size == 0:
                continue
            lo = float(np.percentile(block, black_pct))
            hi = float(np.percentile(block, white_pct))
            if (hi - lo) < uniform_floor:
                # Uniform tile — pass the raw signal straight through.
                tile_uniform[ti, tj] = True
                tile_lo[ti, tj] = 0.0
                tile_hi[ti, tj] = 1.0
            else:
                tile_lo[ti, tj] = lo
                tile_hi[ti, tj] = hi

    # Per-pixel index into the tile grid (with bilinear weights).
    yy = np.arange(H)
    xx = np.arange(W)
    iy = np.clip(np.searchsorted(cy, yy) - 1, 0, g - 2)
    ix = np.clip(np.searchsorted(cx, xx) - 1, 0, g - 2)

    cy_lo = cy[iy]
    cy_hi = cy[iy + 1]
    cx_lo = cx[ix]
    cx_hi = cx[ix + 1]
    wy = ((yy - cy_lo) / np.maximum(cy_hi - cy_lo, 1e-6)).clip(0, 1).astype(np.float32)
    wx = ((xx - cx_lo) / np.maximum(cx_hi - cx_lo, 1e-6)).clip(0, 1).astype(np.float32)

    iy = iy[:, None]
    ix = ix[None, :]
    wy = wy[:, None]
    wx = wx[None, :]

    def under(ti, tj):
        lo = tile_lo[ti, tj]
        hi = tile_hi[ti, tj]
        uni = tile_uniform[ti, tj]
        spread = np.maximum(hi - lo, 1e-3)
        stretched = np.clip((signal - lo) / spread, 0.0, 1.0)
        return np.where(uni, signal, stretched)

    a = under(iy, ix)
    b = under(iy, ix + 1)
    c = under(iy + 1, ix)
    d = under(iy + 1, ix + 1)
    top = a * (1 - wx) + b * wx
    bot = c * (1 - wx) + d * wx
    out = top * (1 - wy) + bot * wy
    return np.clip(out.astype(np.float32), 0.0, 1.0)


# ---------------------------------------------------------------------------
# Edge magnitude
# ---------------------------------------------------------------------------


def _sobel_magnitude(lum: np.ndarray) -> np.ndarray:
    """3x3 Sobel edge magnitude, normalised to [0, 1]."""
    p = np.pad(lum.astype(np.float32, copy=False), 1, mode="edge")
    gx = (-1.0 * p[0:-2, 0:-2] + 1.0 * p[0:-2, 2:]
          + -2.0 * p[1:-1, 0:-2] + 2.0 * p[1:-1, 2:]
          + -1.0 * p[2:,   0:-2] + 1.0 * p[2:,   2:])
    gy = (-1.0 * p[0:-2, 0:-2] + -2.0 * p[0:-2, 1:-1] + -1.0 * p[0:-2, 2:]
          +  1.0 * p[2:,   0:-2] +  2.0 * p[2:,   1:-1] +  1.0 * p[2:,   2:])
    mag = np.sqrt(gx * gx + gy * gy, dtype=np.float32)
    # Max possible Sobel magnitude on [0,1] input is ~5.66; 4.0 keeps
    # typical edges inside [0, 1] without clipping rare strong ones.
    return np.clip(mag * (1.0 / 4.0), 0.0, 1.0)


# ---------------------------------------------------------------------------
# Tone curve
# ---------------------------------------------------------------------------


def _tone_curve(signal: np.ndarray, gamma: float) -> np.ndarray:
    """Apply a power tone curve. ``gamma > 1`` darkens mid-tones; the
    default ``1.2`` is a soft compression that keeps mid-tones light
    while still preventing forest/landuse mid-tones from flooding to
    solid mass."""
    g = max(0.05, float(gamma))
    return np.power(np.clip(signal, 0.0, 1.0), g, dtype=np.float32)


def _quantise(signal: np.ndarray, levels: int) -> np.ndarray:
    """Map a [0, 1] signal to integer fill levels in [0, levels-1]."""
    levels = max(2, int(levels))
    out = np.round(signal * (levels - 1)).astype(np.int32)
    return np.clip(out, 0, levels - 1).astype(np.uint8)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Default tone-curve exponent. 1.2 gives a gentle compression: sharp
# features at signal 0.9 land at fill 0.88 (near-full); mid-tones at
# signal 0.5 land at fill 0.43 (mid-shade). Compare with v1.0.2's
# value of 2.0 which crushed signal 0.5 down to 0.25.
_DEFAULT_GAMMA = 1.2


def compute_fill_levels(
    lum: np.ndarray,
    levels: int,
    threshold_mode: str = "adaptive",
    percentile: float = 55.0,
    tile_grid: int = 4,
    signal_floor: float = 0.06,
    signal_gamma: float = _DEFAULT_GAMMA,
) -> np.ndarray:
    """Map a luminance image to per-pixel fill levels.

    See module docstring for the four mode presets.

    ``signal_gamma`` shapes the tone curve. ``1.0`` is fully linear
    (brightest, mid-tones stand out most); ``1.2`` (default) is a
    soft compression; ``2.0`` is the v1.0.2 darker look.
    """
    levels = max(2, int(levels))

    # Step 1: orient.
    sig = _orient_signal(lum)

    # Edge mode mixes a Sobel edge map into the signal so thin features
    # on a uniform field still register.
    if threshold_mode == "edge":
        edges = _sobel_magnitude(lum)
        sig = np.clip(0.6 * sig + 0.8 * edges, 0.0, 1.0)

    p = _params_for(threshold_mode)

    # Step 2: stretch.
    if p.use_local_stretch:
        sig = _adaptive_local_stretch(
            sig, tile_grid=tile_grid,
            black_pct=p.black_pct, white_pct=p.white_pct,
            uniform_floor=signal_floor,
        )
    else:
        # The legacy `percentile` knob nudges the white point in
        # `percentile` mode; other modes use their preset.
        white_pct = p.white_pct
        if threshold_mode == "percentile":
            white_pct = float(np.clip(40.0 + percentile, 80.0, 99.0))
        sig = _global_stretch(sig, p.black_pct, white_pct)

    # Step 3: tone curve.
    sig = _tone_curve(sig, signal_gamma)

    # Step 4: quantise.
    return _quantise(sig, levels)


def compute_binary_fill(
    lum: np.ndarray,
    threshold_mode: str = "adaptive",
    percentile: float = 55.0,
    tile_grid: int = 4,
    signal_floor: float = 0.06,
) -> np.ndarray:
    """Return a 0/1 mask, same shape as ``lum``, marking 'filled'
    pixels.

    For ``threshold_mode="edge"`` the mask is taken directly from the
    edge magnitude — that's what makes faint features on uniform
    backgrounds (the canonical use case for edge mode at extreme zoom)
    actually visible in 1-bit output.
    """
    if threshold_mode == "edge":
        edges = _sobel_magnitude(lum)
        cutoff = float(np.percentile(edges, max(50.0, 100.0 - percentile / 2.0)))
        cutoff = max(cutoff, 0.04)
        return (edges > cutoff).astype(np.uint8)

    sig = _orient_signal(lum)
    p = _params_for(threshold_mode)

    if p.use_local_stretch:
        sig = _adaptive_local_stretch(
            sig, tile_grid=tile_grid,
            black_pct=p.black_pct, white_pct=p.white_pct,
            uniform_floor=signal_floor,
        )
    else:
        white_pct = p.white_pct
        if threshold_mode == "percentile":
            white_pct = float(np.clip(40.0 + percentile, 80.0, 99.0))
        sig = _global_stretch(sig, p.black_pct, white_pct)

    return (sig > 0.5).astype(np.uint8)
