"""Threshold and subpixel-fill helpers for the renderer.

The terminal cell is too coarse to render every pixel directly, so we map
luminance (and optionally local contrast) to a *fill level* per subpixel.

Three thresholding strategies:

  * ``fixed`` — single 0.5 luminance threshold (pre-v0.7 behaviour).
  * ``percentile`` — picks the threshold from the image's actual luminance
    distribution; auto-detects whether features are darker or lighter than
    the background. Good when the image has a balanced histogram.
  * ``edge`` — Sobel-style local contrast detection. Robust at extreme zooms
    where the image is mostly a single colour with thin features.

Each strategy returns a same-shape uint8 array of *fill levels* in
``[0, levels-1]`` where ``levels`` is the number of palette steps.
For 1-bit modes ``levels=2`` and the result is a binary fill mask.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "compute_fill_levels",
    "compute_binary_fill",
    "estimate_orientation",
]


def estimate_orientation(lum: np.ndarray) -> str:
    """Return ``"dark"`` or ``"bright"`` for the image's overall character.

    Used so we know whether features are *brighter than* or *darker than* the
    background — the answer flips the meaning of "filled".
    """
    return "dark" if float(lum.mean()) < 0.4 else "bright"


def _sobel_edges(lum: np.ndarray) -> np.ndarray:
    """Approximate edge-magnitude via 3×3 Sobel kernels (separable)."""
    # Pad with edge replication so output keeps shape.
    p = np.pad(lum, 1, mode="edge")
    # Horizontal gradient
    gx = (
        -1.0 * p[0:-2, 0:-2] + 1.0 * p[0:-2, 2:]
        + -2.0 * p[1:-1, 0:-2] + 2.0 * p[1:-1, 2:]
        + -1.0 * p[2:,   0:-2] + 1.0 * p[2:,   2:]
    )
    gy = (
        -1.0 * p[0:-2, 0:-2] + -2.0 * p[0:-2, 1:-1] + -1.0 * p[0:-2, 2:]
        +  1.0 * p[2:,   0:-2] +  2.0 * p[2:,   1:-1] +  1.0 * p[2:,   2:]
    )
    mag = np.sqrt(gx * gx + gy * gy)
    # Normalise to [0,1]; max possible Sobel magnitude on [0,1] input is ~5.66.
    return np.clip(mag / 4.0, 0.0, 1.0)


def compute_binary_fill(
    lum: np.ndarray,
    threshold_mode: str = "percentile",
    percentile: float = 55.0,
) -> np.ndarray:
    """Return a 0/1 mask, same shape as ``lum``, marking 'filled' pixels."""
    if threshold_mode == "fixed":
        return (lum < 0.5).astype(np.uint8)

    if threshold_mode == "edge":
        edges = _sobel_edges(lum)
        # Pick a threshold from the edge map's distribution. For images with
        # very few edges (uniform regions) this still produces a sparse but
        # non-empty mask.
        thr = float(np.percentile(edges, 100 - percentile / 2.0))
        thr = max(thr, 0.04)  # floor — never mark literally everything as edge
        return (edges > thr).astype(np.uint8)

    # percentile (default), with orientation detection
    orient = estimate_orientation(lum)
    if orient == "dark":
        thr = float(np.percentile(lum, 100 - percentile))
        return (lum > thr).astype(np.uint8)
    thr = float(np.percentile(lum, percentile))
    return (lum < thr).astype(np.uint8)


def compute_fill_levels(
    lum: np.ndarray,
    levels: int,
    threshold_mode: str = "percentile",
    percentile: float = 55.0,
) -> np.ndarray:
    """Return per-pixel fill levels in ``[0, levels-1]``.

    For ``levels == 2`` this is equivalent to ``compute_binary_fill``.
    For ``levels > 2`` this drives multi-step density (palette-driven fill).

    Edge mode is special-cased to combine luminance with the edge magnitude
    so feature pixels boost above their luminance-only level.
    """
    levels = max(2, int(levels))

    if threshold_mode == "fixed":
        # Map luminance directly to levels, dark = high fill.
        return np.clip(
            np.round((1.0 - lum) * (levels - 1)).astype(np.int32),
            0, levels - 1,
        ).astype(np.uint8)

    if threshold_mode == "edge":
        edges = _sobel_edges(lum)
        # Combine: base from luminance, boosted in edge regions.
        orient = estimate_orientation(lum)
        if orient == "dark":
            base = lum  # dark images: bright pixels are features
        else:
            base = 1.0 - lum
        # Stretch base into a usable contrast range.
        b_min = float(np.percentile(base, 5))
        b_max = float(np.percentile(base, 95))
        if b_max > b_min:
            base = np.clip((base - b_min) / (b_max - b_min), 0.0, 1.0)
        # Add edge contribution.
        signal = np.clip(0.6 * base + 1.4 * edges, 0.0, 1.0)
        return np.clip(
            np.round(signal * (levels - 1)).astype(np.int32),
            0, levels - 1,
        ).astype(np.uint8)

    # percentile mode with orientation detection.
    orient = estimate_orientation(lum)
    if orient == "dark":
        # Bright = feature; map 0 (dark/empty) → 0, bright → high level.
        signal = lum
    else:
        signal = 1.0 - lum
    # Histogram-stretch signal so the palette levels actually span the image.
    s_min = float(np.percentile(signal, 100 - percentile))
    s_max = float(np.percentile(signal, max(95.0, percentile + 5.0)))
    if s_max <= s_min + 1e-6:
        # Histogram is collapsed at the chosen percentiles — most of the image
        # is the same brightness with a small fraction of features. Push s_max
        # up to the actual maximum so feature pixels still register.
        s_max = float(signal.max())
    if s_max > s_min + 1e-6:
        signal = np.clip((signal - s_min) / (s_max - s_min), 0.0, 1.0)
    else:
        signal = np.zeros_like(signal)
    return np.clip(
        np.round(signal * (levels - 1)).astype(np.int32),
        0, levels - 1,
    ).astype(np.uint8)
