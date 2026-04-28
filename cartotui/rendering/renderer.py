"""Renderer dispatcher and three backends: ASCII, quadrant, braille.

A render pass turns a Pillow RGB image into a list of styled rows suitable for
prompt_toolkit's `FormattedText`. Each row is a list of (style, text) runs;
adjacent cells with the same colour are merged so terminal output is compact.

Backends:
  * ASCII     — one cell per char, palette glyph by luminance, optional dither.
  * Quadrant  — 2×2 subpixels per cell using Unicode block elements.
  * Braille   — 2×4 subpixels per cell using Unicode braille patterns.

# Smart braille → quadrant fallback

Braille is great for rendering vector geometry (sharp 1-bit roads,
building outlines) because each braille cell encodes 8 binary
sub-pixels and the *binary-ness* matches the source. It's a bad fit
for continuous-tone raster tiles (OSM-style cream-and-grey terrain
with overlaid antialiased lines): every sub-pixel makes its own
threshold decision, so flat land regions speckle and you can't read
anything.

The renderer detects this combination and silently downgrades to
quadrant mode unless the caller explicitly opts out. The signal
comes from the new ``source_kind`` argument to ``Renderer.render()``:
when it's ``"raster"`` and ``mode == "braille"``, we route to the
quadrant backend instead. The caller is told what happened via
``Renderer.last_effective_mode`` so the status bar can show e.g.
``BRAILLE→QUAD``.

This can be turned off with ``auto_downgrade_braille_on_raster=False``
on the Renderer for users who want the old behaviour back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from cartotui.rendering import dither as dither_mod
from cartotui.rendering.threshold import (
    compute_fill_levels,
)

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

__all__ = [
    "Renderer",
    "AsciiBackend",
    "QuadrantBackend",
    "BrailleBackend",
    "default_palettes",
]


def default_palettes() -> Dict[str, str]:
    return {
        # The keeper from the old set — uniform-width block shading.
        "shades":     " ░▒▓█",
        # Fine 8-step block shading for richer tonal range.
        "blocks":     " ▁▂▃▄▅▆▇█",
        # Dot density palette — sparse to dense circular fill.
        "dots":       " ·∙•●⬤",
        # Hatching — diagonal stripes, evokes old map fills.
        "hatch":      " ░▒▓",
        # Ink — high-contrast 3-step for strong B&W cartography look.
        "ink":        " ▒█",
        # Topographic — block shades plus solid for "altitude" feel.
        "topo":       " ░▒▓█▓▒░ ",
        # Heatmap-style — uses block elements for density steps.
        "heat":       " ░▒▓█",
        # Mono dot — pure 2-level for crispest line work.
        "binary":     " █",
        # DOS-style 11-step ASCII ramp — the classic text-art look.
        # Pairs especially well with quadrant mode + bayer dither for
        # a recognisable "Magellan / Garmin / DOS GPS" feel.
        "dos":        " .,:;+=*#%@",
        # Same idea but coarser, 5 steps — good when you want the look
        # without the density of the full ramp at small terminals.
        "dos5":       " .+#@",
    }


def _rgb_to_style(r: int, g: int, b: int) -> str:
    return f"fg:#{r:02x}{g:02x}{b:02x}"


def _luminance(arr_u8: np.ndarray) -> np.ndarray:
    """Return Rec. 601 luminance in [0, 1] for an HxWx3 uint8 array."""
    return (
        0.299 * arr_u8[..., 0]
        + 0.587 * arr_u8[..., 1]
        + 0.114 * arr_u8[..., 2]
    ).astype(np.float32) / 255.0


def _quantize(lum: np.ndarray, levels: int, mode: str) -> np.ndarray:
    if mode == "atkinson":
        return dither_mod.atkinson(lum, levels)
    if mode == "bayer":
        return dither_mod.bayer(lum, levels)
    if mode == "floyd":
        return dither_mod.floyd_steinberg(lum, levels)
    return dither_mod.quantize_no_dither(lum, levels)


def _emit_row(glyphs: List[str], styles: List[str]) -> LineFrag:
    """Run-length-encode (style, glyph) pairs into a LineFrag."""
    if not glyphs:
        return [("", "")]
    out: LineFrag = []
    cur_style = styles[0]
    buf: List[str] = [glyphs[0]]
    for ch, st in zip(glyphs[1:], styles[1:]):
        if st == cur_style:
            buf.append(ch)
        else:
            out.append((cur_style, "".join(buf)))
            cur_style = st
            buf = [ch]
    out.append((cur_style, "".join(buf)))
    return out


def _emit_row_color_fast(
    glyphs: np.ndarray,    # 1-D array of single-char strings, shape (W,)
    rgb: np.ndarray,       # 2-D uint8 array shape (W, 3)
) -> LineFrag:
    """Vectorised colour RLE. Builds a packed int per cell, finds runs in
    numpy, and only formats the style string per *run* — not per pixel."""
    w = rgb.shape[0]
    if w == 0:
        return [("", "")]
    packed = (rgb[:, 0].astype(np.int32) << 16) | (rgb[:, 1].astype(np.int32) << 8) | rgb[:, 2].astype(np.int32)
    diff = np.empty(w, dtype=bool)
    diff[0] = True
    diff[1:] = packed[1:] != packed[:-1]
    starts = np.flatnonzero(diff)
    ends = np.concatenate([starts[1:], np.array([w], dtype=np.intp)])
    out: LineFrag = []
    glyph_list = glyphs.tolist() if isinstance(glyphs, np.ndarray) else list(glyphs)
    for s, e in zip(starts.tolist(), ends.tolist()):
        v = int(packed[s])
        style = f"fg:#{v:06x}"
        out.append((style, "".join(glyph_list[s:e])))
    return out


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class AsciiBackend:
    name = "ascii"

    def __init__(
        self,
        threshold_mode: str = "adaptive",
        percentile: float = 55.0,
        shaded: bool = False,
    ) -> None:
        self.threshold_mode = threshold_mode
        self.percentile = float(percentile)
        # `shaded` is unused in ASCII mode but accepted so the constructor is
        # uniform across backends.
        self.shaded = bool(shaded)

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str,
        dither: str = "none",
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width != term_w or img.height != term_h:
            img = img.resize((term_w, term_h), Image.LANCZOS)

        arr = np.asarray(img, dtype=np.uint8)
        lum = _luminance(arr)
        glyph_chars = list(palette) if palette else list(" .")
        levels = len(glyph_chars)
        if dither and dither != "none":
            # Flip orientation so 'feature' pixels (the contrast we want to
            # see) become the high-luminance end of the dither input. After
            # this, dither distributes error correctly on both light and
            # dark themes.
            from cartotui.rendering.threshold import estimate_orientation
            flip_lum = lum if estimate_orientation(lum) == "dark" else (1.0 - lum)
            idx = _quantize(flip_lum, levels, dither)
        else:
            idx = compute_fill_levels(
                lum, levels,
                threshold_mode=self.threshold_mode,
                percentile=self.percentile,
            )
        glyphs_arr = np.array(glyph_chars)

        frame: FrameFrag = []
        if use_color:
            for y in range(term_h):
                row_glyphs = glyphs_arr[idx[y]]
                frame.append(_emit_row_color_fast(row_glyphs, arr[y]))
        else:
            for y in range(term_h):
                frame.append([("", "".join(glyphs_arr[idx[y]].tolist()))])
        return frame


# Quadrant glyphs indexed by 4-bit pattern (TL, TR, BL, BR).
_QUAD_GLYPHS = [
    " ", "▗", "▖", "▄",
    "▝", "▐", "▞", "▟",
    "▘", "▚", "▌", "▙",
    "▀", "▜", "▛", "█",
]


class QuadrantBackend:
    name = "quadrant"

    def __init__(
        self,
        threshold_mode: str = "adaptive",
        percentile: float = 55.0,
        shaded: bool = False,
    ) -> None:
        self.threshold_mode = threshold_mode
        self.percentile = float(percentile)
        self.shaded = bool(shaded)

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str,
        dither: str = "none",
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]
        if img.mode != "RGB":
            img = img.convert("RGB")

        target_w = term_w * 2
        target_h = term_h * 2
        if img.width != target_w or img.height != target_h:
            img = img.resize((target_w, target_h), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.uint8)
        lum = _luminance(arr)

        palette_chars = list(palette) if palette else list(" ░▒▓█")
        levels = max(2, len(palette_chars))
        fill = compute_fill_levels(
            lum, levels,
            threshold_mode=self.threshold_mode,
            percentile=self.percentile,
        )

        tl = fill[0::2, 0::2]
        tr = fill[0::2, 1::2]
        bl = fill[1::2, 0::2]
        br = fill[1::2, 1::2]

        cell_max = np.maximum(np.maximum(tl, tr), np.maximum(bl, br))
        cell_min = np.minimum(np.minimum(tl, tr), np.minimum(bl, br))
        cell_avg = (tl.astype(np.int32) + tr + bl + br) // 4

        thr = cell_avg
        codes = (
            ((tl > thr) << 3) | ((tr > thr) << 2)
            | ((bl > thr) << 1) | (br > thr)
        ).astype(np.uint8)

        flat = (cell_max == cell_min)
        full = (cell_min >= levels - 1)
        empty = (cell_max == 0)

        glyph_lookup = np.array(_QUAD_GLYPHS)
        cell_glyphs = glyph_lookup[codes]

        palette_arr = np.array(palette_chars)
        flat_idx = np.clip(cell_avg, 0, levels - 1)
        flat_glyphs = palette_arr[flat_idx]

        cell_glyphs = np.where(flat, flat_glyphs, cell_glyphs)
        cell_glyphs = np.where(empty, palette_arr[0], cell_glyphs)
        cell_glyphs = np.where(full, palette_arr[-1], cell_glyphs)

        if self.shaded:
            partial = ~flat & ~empty & ~full
            heavy = partial & (cell_avg >= max(1, levels // 2))
            soft_glyphs = palette_arr[np.clip(cell_avg, 1, levels - 1)]
            cell_glyphs = np.where(heavy, soft_glyphs, cell_glyphs)

        if use_color:
            r = (arr[0::2, 0::2, 0].astype(np.int32) + arr[0::2, 1::2, 0]
                 + arr[1::2, 0::2, 0] + arr[1::2, 1::2, 0]) // 4
            g = (arr[0::2, 0::2, 1].astype(np.int32) + arr[0::2, 1::2, 1]
                 + arr[1::2, 0::2, 1] + arr[1::2, 1::2, 1]) // 4
            b = (arr[0::2, 0::2, 2].astype(np.int32) + arr[0::2, 1::2, 2]
                 + arr[1::2, 0::2, 2] + arr[1::2, 1::2, 2]) // 4
            cell_rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)

        frame: FrameFrag = []
        for y in range(term_h):
            if use_color:
                frame.append(_emit_row_color_fast(cell_glyphs[y], cell_rgb[y]))
            else:
                frame.append([("", "".join(cell_glyphs[y].tolist()))])
        return frame


# Braille bit positions per (row, col) in a 4×2 sub-pixel block.
_BRAILLE_BITS = np.array(
    [
        [0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80],
    ],
    dtype=np.uint8,
)


class BrailleBackend:
    name = "braille"

    def __init__(
        self,
        threshold_mode: str = "adaptive",
        percentile: float = 55.0,
        shaded: bool = False,
    ) -> None:
        self.threshold_mode = threshold_mode
        self.percentile = float(percentile)
        self.shaded = bool(shaded)

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str,
        dither: str = "none",
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]
        if img.mode != "RGB":
            img = img.convert("RGB")

        target_w = term_w * 2
        target_h = term_h * 4
        if img.width != target_w or img.height != target_h:
            img = img.resize((target_w, target_h), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.uint8)
        lum = _luminance(arr)

        palette_chars = list(palette) if palette else list(" ░▒▓█")
        levels = max(2, len(palette_chars))
        fill = compute_fill_levels(
            lum, levels,
            threshold_mode=self.threshold_mode,
            percentile=self.percentile,
        )

        cell_avg = fill.reshape(term_h, 4, term_w, 2).mean(axis=(1, 3))

        thr = np.repeat(np.repeat(cell_avg, 4, axis=0), 2, axis=1)
        filled = (fill > thr).astype(np.uint8)

        codes = np.zeros((term_h, term_w), dtype=np.uint8)
        for ry in range(4):
            for cx in range(2):
                codes |= filled[ry::4, cx::2] * _BRAILLE_BITS[ry, cx]

        glyphs_int = codes.astype(np.int32) + 0x2800

        flat = (codes == 0) | (codes == 0xFF)
        palette_codes = np.array([ord(c) for c in palette_chars], dtype=np.int32)
        flat_idx = np.clip(cell_avg.astype(np.int32), 0, levels - 1)
        flat_glyphs = palette_codes[flat_idx]
        glyphs_int = np.where(flat, flat_glyphs, glyphs_int)

        if self.shaded and palette:
            popcount = np.unpackbits(codes[..., None], axis=-1).sum(axis=-1)
            heavy = popcount >= 6
            soft = palette_codes[np.clip(cell_avg.astype(np.int32), 1, levels - 1)]
            glyphs_int = np.where(heavy, soft, glyphs_int)

        frame: FrameFrag = []
        if use_color:
            r = arr[..., 0].reshape(term_h, 4, term_w, 2).mean(axis=(1, 3)).astype(np.int32)
            g = arr[..., 1].reshape(term_h, 4, term_w, 2).mean(axis=(1, 3)).astype(np.int32)
            b = arr[..., 2].reshape(term_h, 4, term_w, 2).mean(axis=(1, 3)).astype(np.int32)
            cell_rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
            for y in range(term_h):
                row_glyphs = np.array([chr(int(c)) for c in glyphs_int[y]])
                frame.append(_emit_row_color_fast(row_glyphs, cell_rgb[y]))
        else:
            for y in range(term_h):
                frame.append([("", "".join(chr(int(c)) for c in glyphs_int[y]))])
        return frame


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@dataclass
class Renderer:
    palettes: Dict[str, str]
    default_palette: str = "shades"
    subpixel_threshold: str = "adaptive"
    subpixel_percentile: float = 55.0
    shaded_blocks: bool = False
    # When True (default), feeding a raster source into braille mode
    # silently downgrades to quadrant. Continuous-tone raster + 8
    # binary sub-pixels per cell = unreadable speckle. The downgrade
    # gives flat tonal regions a single palette glyph per cell instead
    # of a randomised stipple. Set False to opt out.
    auto_downgrade_braille_on_raster: bool = True
    # Last mode actually used by render(). Different from the requested
    # mode iff the auto-downgrade fired. The status bar reads this.
    last_effective_mode: str = field(default="ascii", init=False)

    def __post_init__(self) -> None:
        self._backends: Dict[str, object] = {
            "ascii":    AsciiBackend(
                threshold_mode=self.subpixel_threshold,
                percentile=self.subpixel_percentile,
                shaded=self.shaded_blocks,
            ),
            "quadrant": QuadrantBackend(
                threshold_mode=self.subpixel_threshold,
                percentile=self.subpixel_percentile,
                shaded=self.shaded_blocks,
            ),
            "braille":  BrailleBackend(
                threshold_mode=self.subpixel_threshold,
                percentile=self.subpixel_percentile,
                shaded=self.shaded_blocks,
            ),
        }

    def update_options(
        self,
        subpixel_threshold: Optional[str] = None,
        subpixel_percentile: Optional[float] = None,
        shaded_blocks: Optional[bool] = None,
    ) -> None:
        if subpixel_threshold is not None:
            self.subpixel_threshold = subpixel_threshold
        if subpixel_percentile is not None:
            self.subpixel_percentile = subpixel_percentile
        if shaded_blocks is not None:
            self.shaded_blocks = shaded_blocks
        kwargs = dict(
            threshold_mode=self.subpixel_threshold,
            percentile=self.subpixel_percentile,
            shaded=self.shaded_blocks,
        )
        self._backends["ascii"] = AsciiBackend(**kwargs)
        self._backends["quadrant"] = QuadrantBackend(**kwargs)
        self._backends["braille"] = BrailleBackend(**kwargs)

    def register(self, mode: str, backend: object) -> None:
        self._backends[mode] = backend

    def get_palette(self, name: Optional[str]) -> str:
        if name and name in self.palettes:
            return self.palettes[name]
        if self.default_palette in self.palettes:
            return self.palettes[self.default_palette]
        return next(iter(self.palettes.values()), " .")

    def cell_pixel_size(self, mode: str) -> Tuple[int, int]:
        """Return (width_px, height_px) per character cell for the given mode."""
        if mode == "quadrant":
            return 2, 2
        if mode == "braille":
            return 2, 4
        return 1, 2  # ASCII: roughly square character footprint

    def _resolve_mode(self, mode: str, source_kind: Optional[str]) -> str:
        """Apply the auto-downgrade rule. Returns the mode actually used.

        Continuous-tone raster + 8 binary braille sub-pixels per cell is
        the canonical "completely unreadable" combination — flat land
        regions of a 50% grey raster tile have noisy luminance, the
        sub-pixel threshold flips on every neighbour, and the cell
        becomes a randomised stipple instead of a coherent shade. Even
        the threshold rewrite can't save this — the information density
        is wrong for the destination format. The fix is to use a
        2x2-subpixel cell instead, which thresholds 4 sub-pixels and
        almost always finds them all on the same side, so cells become
        single palette glyphs instead of stippled noise.
        """
        if mode != "braille":
            return mode
        if source_kind != "raster":
            return mode
        if not self.auto_downgrade_braille_on_raster:
            return mode
        return "quadrant"

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        mode: str = "ascii",
        palette_name: Optional[str] = None,
        dither: str = "none",
        source_kind: Optional[str] = None,
    ) -> FrameFrag:
        """Render an image to a list of styled rows.

        ``source_kind`` is a hint to the dispatcher: ``"raster"`` for
        OSM-style continuous-tone tiles, ``"vector"`` for the output of
        the vector rasteriser (binary-ish geometry already), ``None``
        when the caller doesn't know. ``None`` is treated as "no
        downgrade hint" — equivalent to ``"vector"`` for routing
        purposes — which preserves backward compatibility for callers
        that pre-date the smart-downgrade.
        """
        effective_mode = self._resolve_mode(mode, source_kind)
        self.last_effective_mode = effective_mode
        backend = self._backends.get(effective_mode) or self._backends["ascii"]
        return backend.render(
            img,
            term_w,
            term_h,
            use_color,
            self.get_palette(palette_name),
            dither,
        )
