
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
        "shades":     " ░▒▓█",
        "blocks":     " ▁▂▃▄▅▆▇█",
        "dots":       " ·∙•●⬤",
        "hatch":      " ░▒▓",
        "ink":        " ▒█",
        "topo":       " ░▒▓█▓▒░ ",
        "heat":       " ░▒▓█",
        "binary":     " █",
        "dos":        " .,:;+=*#%@",
        "dos5":       " .+#@",
    }

def _rgb_to_style(r: int, g: int, b: int) -> str:
    return f"fg:#{r:02x}{g:02x}{b:02x}"

def _resample(img: Image.Image, tw: int, th: int) -> Image.Image:
    w, h = img.width, img.height
    if w == tw and h == th:
        return img
    if w >= tw and h >= th:
        if w % tw == 0 and h % th == 0 and (w // tw > 1 or h // th > 1):
            return img.reduce((w // tw, h // th))
        return img.resize((tw, th), Image.BOX)
    return img.resize((tw, th), Image.LANCZOS)

def _luminance(arr_u8: np.ndarray) -> np.ndarray:
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

_FG_CACHE: Dict[int, str] = {}
_HB_CACHE: Dict[int, str] = {}

def _fg_style(v: int) -> str:
    s = _FG_CACHE.get(v)
    if s is None:
        s = f"fg:#{v:06x}"
        if len(_FG_CACHE) < 65536:
            _FG_CACHE[v] = s
    return s

def _emit_row_color_fast(
    glyphs: np.ndarray,
    rgb: np.ndarray,
) -> LineFrag:
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
        out.append((_fg_style(int(packed[s])), "".join(glyph_list[s:e])))
    return out

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
            img = _resample(img, term_w, term_h)

        arr = np.asarray(img, dtype=np.uint8)
        lum = _luminance(arr)
        glyph_chars = list(palette) if palette else list(" .")
        levels = len(glyph_chars)
        if dither and dither != "none":
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
            img = _resample(img, target_w, target_h)
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
            img = _resample(img, target_w, target_h)
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
            fr = filled.reshape(term_h, 4, term_w, 2).astype(np.float32)
            cnt = fr.sum(axis=(1, 3))
            inv = 1.0 / np.maximum(cnt, 1.0)

            def _cell_color(ch: int) -> np.ndarray:
                c = arr[..., ch].astype(np.float32).reshape(term_h, 4, term_w, 2)
                lit = (c * fr).sum(axis=(1, 3)) * inv
                whole = c.mean(axis=(1, 3))
                return np.where(cnt > 0, lit, whole)

            cell_rgb = np.stack(
                [_cell_color(0), _cell_color(1), _cell_color(2)], axis=-1
            ).clip(0, 255).astype(np.uint8)
            for y in range(term_h):
                row_glyphs = np.array([chr(int(c)) for c in glyphs_int[y]])
                frame.append(_emit_row_color_fast(row_glyphs, cell_rgb[y]))
        else:
            for y in range(term_h):
                frame.append([("", "".join(chr(int(c)) for c in glyphs_int[y]))])
        return frame

def _emit_halfblock_row(top: np.ndarray, bot: np.ndarray) -> LineFrag:
    w = top.shape[0]
    if w == 0:
        return [("", "")]
    tp = (top[:, 0].astype(np.int64) << 16) | (top[:, 1].astype(np.int64) << 8) | top[:, 2]
    bp = (bot[:, 0].astype(np.int64) << 16) | (bot[:, 1].astype(np.int64) << 8) | bot[:, 2]
    key = (tp << 24) | bp
    diff = np.empty(w, dtype=bool)
    diff[0] = True
    diff[1:] = key[1:] != key[:-1]
    starts = np.flatnonzero(diff)
    ends = np.concatenate([starts[1:], np.array([w], dtype=np.intp)])
    out: LineFrag = []
    for s, e in zip(starts.tolist(), ends.tolist()):
        t = int(tp[s])
        b = int(bp[s])
        hk = (t << 24) | b
        style = _HB_CACHE.get(hk)
        if style is None:
            style = f"fg:#{t:06x} bg:#{b:06x}"
            if len(_HB_CACHE) < 200000:
                _HB_CACHE[hk] = style
        out.append((style, "▀" * (e - s)))
    return out

class HalfBlockBackend:
    name = "half"

    def __init__(self, **_kwargs) -> None:
        pass

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
        tw, th = term_w, term_h * 2
        if img.width != tw or img.height != th:
            img = _resample(img, tw, th)
        arr = np.asarray(img, dtype=np.uint8)
        if not use_color:
            g = (_luminance(arr) * 255.0).astype(np.uint8)
            arr = np.stack([g, g, g], axis=-1)
        top = arr[0::2]
        bot = arr[1::2]
        n = min(top.shape[0], bot.shape[0])
        frame: FrameFrag = []
        for y in range(n):
            frame.append(_emit_halfblock_row(top[y], bot[y]))
        return frame

@dataclass
class Renderer:
    palettes: Dict[str, str]
    default_palette: str = "shades"
    subpixel_threshold: str = "adaptive"
    subpixel_percentile: float = 55.0
    shaded_blocks: bool = False
    auto_downgrade_braille_on_raster: bool = True
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
            "half":     HalfBlockBackend(),
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
        self._backends["half"] = HalfBlockBackend()

    def register(self, mode: str, backend: object) -> None:
        self._backends[mode] = backend

    def get_palette(self, name: Optional[str]) -> str:
        if name and name in self.palettes:
            return self.palettes[name]
        if self.default_palette in self.palettes:
            return self.palettes[self.default_palette]
        return next(iter(self.palettes.values()), " .")

    def cell_pixel_size(self, mode: str) -> Tuple[int, int]:
        if mode == "quadrant":
            return 2, 4
        if mode == "braille":
            return 2, 4
        if mode == "half":
            return 1, 2
        return 1, 2

    def _resolve_mode(self, mode: str, source_kind: Optional[str]) -> str:
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
