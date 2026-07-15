
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

__all__ = [
    "compute_fill_levels",
    "compute_binary_fill",
    "estimate_orientation",
]

_OVERLAY_FLOOR = 0.35

@dataclass(frozen=True)
class _ModeParams:

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
        return _ModeParams(False, 0.0, 100.0, False)
    return _ModeParams(False, 8.0, 96.0, False)

def estimate_orientation(lum: np.ndarray) -> str:
    """Guess whether a frame is light-on-dark ("dark") or ink-on-paper ("bright").

    Only a fallback. Guessing from the frame mean means any tone knob that drags
    the mean across the threshold flips the glyph ramp and visibly inverts the
    map mid-adjustment, so callers that know the polarity should say so.
    """
    return "dark" if float(lum.mean()) < 0.4 else "bright"

def _orient_signal(lum: np.ndarray, orientation: Optional[str] = None) -> np.ndarray:
    if orientation not in ("dark", "bright"):
        orientation = estimate_orientation(lum)
    if orientation == "dark":
        return lum.astype(np.float32, copy=False)
    return (1.0 - lum).astype(np.float32, copy=False)

def _global_stretch(signal: np.ndarray, black_pct: float, white_pct: float) -> np.ndarray:
    if black_pct <= 0.0 and white_pct >= 100.0:
        return np.clip(signal, 0.0, 1.0)
    lo = float(np.percentile(signal, black_pct))
    hi = float(np.percentile(signal, white_pct))
    if hi - lo < 1e-3:
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
                tile_uniform[ti, tj] = True
                tile_lo[ti, tj] = 0.0
                tile_hi[ti, tj] = 1.0
            else:
                tile_lo[ti, tj] = lo
                tile_hi[ti, tj] = hi

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

def _sobel_magnitude(lum: np.ndarray) -> np.ndarray:
    p = np.pad(lum.astype(np.float32, copy=False), 1, mode="edge")
    gx = (-1.0 * p[0:-2, 0:-2] + 1.0 * p[0:-2, 2:]
          + -2.0 * p[1:-1, 0:-2] + 2.0 * p[1:-1, 2:]
          + -1.0 * p[2:,   0:-2] + 1.0 * p[2:,   2:])
    gy = (-1.0 * p[0:-2, 0:-2] + -2.0 * p[0:-2, 1:-1] + -1.0 * p[0:-2, 2:]
          +  1.0 * p[2:,   0:-2] +  2.0 * p[2:,   1:-1] +  1.0 * p[2:,   2:])
    mag = np.sqrt(gx * gx + gy * gy, dtype=np.float32)
    return np.clip(mag * (1.0 / 4.0), 0.0, 1.0)

def _blend_overlay(
    signal: np.ndarray,
    overlay_lum: np.ndarray,
    overlay_alpha: np.ndarray,
) -> np.ndarray:
    """Lay a translucent overlay onto an already-normalised map signal.

    The overlay is stretched across its *own* intensity range instead of the
    map's, so light-vs-heavy precipitation stays legible even in mono where the
    glyph carries all the information. Blending by alpha keeps partial coverage
    and the overlay's soft edges intact.
    """
    a = np.clip(overlay_alpha.astype(np.float32, copy=False), 0.0, 1.0)
    covered = a > 0.0
    if not covered.any():
        return signal

    vals = overlay_lum[covered]
    lo = float(np.percentile(vals, 5.0))
    hi = float(np.percentile(vals, 95.0))
    if hi - lo < 1e-3:
        own = np.ones_like(overlay_lum, dtype=np.float32)
    else:
        own = np.clip((overlay_lum - lo) / (hi - lo), 0.0, 1.0)

    band = _OVERLAY_FLOOR + own * (1.0 - _OVERLAY_FLOOR)
    return np.clip(signal * (1.0 - a) + band * a, 0.0, 1.0).astype(np.float32)

def _tone_curve(signal: np.ndarray, gamma: float) -> np.ndarray:
    g = max(0.05, float(gamma))
    return np.power(np.clip(signal, 0.0, 1.0), g, dtype=np.float32)

def _quantise(signal: np.ndarray, levels: int) -> np.ndarray:
    levels = max(2, int(levels))
    out = np.round(signal * (levels - 1)).astype(np.int32)
    return np.clip(out, 0, levels - 1).astype(np.uint8)

_DEFAULT_GAMMA = 1.2

def compute_fill_levels(
    lum: np.ndarray,
    levels: int,
    threshold_mode: str = "adaptive",
    percentile: float = 55.0,
    tile_grid: int = 4,
    signal_floor: float = 0.06,
    signal_gamma: float = _DEFAULT_GAMMA,
    overlay_lum: Optional[np.ndarray] = None,
    overlay_alpha: Optional[np.ndarray] = None,
    orientation: Optional[str] = None,
) -> np.ndarray:
    """Quantise `lum` to `levels` fill steps.

    `lum` must be the base map only. Translucent overlays go through
    `overlay_lum`/`overlay_alpha` so their brightness never enters the map's
    percentiles -- a radar cell over the ocean would otherwise redefine the
    white point and crush the whole viewport toward black.

    `orientation` pins the ink polarity ("dark"/"bright"); left to guess, a
    tone-adjusted frame can flip it and come out inverted.
    """
    levels = max(2, int(levels))

    sig = _orient_signal(lum, orientation)

    if threshold_mode == "edge":
        edges = _sobel_magnitude(lum)
        sig = np.clip(0.6 * sig + 0.8 * edges, 0.0, 1.0)

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

    if overlay_alpha is not None and overlay_lum is not None:
        sig = _blend_overlay(sig, overlay_lum, overlay_alpha)

    sig = _tone_curve(sig, signal_gamma)

    return _quantise(sig, levels)

def compute_binary_fill(
    lum: np.ndarray,
    threshold_mode: str = "adaptive",
    percentile: float = 55.0,
    tile_grid: int = 4,
    signal_floor: float = 0.06,
    overlay_lum: Optional[np.ndarray] = None,
    overlay_alpha: Optional[np.ndarray] = None,
    orientation: Optional[str] = None,
) -> np.ndarray:
    """As `compute_fill_levels`, but a single on/off decision per pixel."""
    if threshold_mode == "edge":
        edges = _sobel_magnitude(lum)
        cutoff = float(np.percentile(edges, max(50.0, 100.0 - percentile / 2.0)))
        cutoff = max(cutoff, 0.04)
        out = (edges > cutoff).astype(np.float32)
        if overlay_alpha is not None and overlay_lum is not None:
            out = _blend_overlay(out, overlay_lum, overlay_alpha)
            return (out > 0.5).astype(np.uint8)
        return out.astype(np.uint8)

    sig = _orient_signal(lum, orientation)
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

    if overlay_alpha is not None and overlay_lum is not None:
        sig = _blend_overlay(sig, overlay_lum, overlay_alpha)

    return (sig > 0.5).astype(np.uint8)
