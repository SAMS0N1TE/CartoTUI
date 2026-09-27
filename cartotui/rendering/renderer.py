
from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from cartotui.rendering import dither as dither_mod
from cartotui.rendering.threshold import (
    compute_fill_levels,
)

log = logging.getLogger("cartotui.render")

# Geographic footprint is independent of glyph sampling and rendering quality.
REFERENCE_SCALE = 3
CELL_MAP_PX = (REFERENCE_SCALE, REFERENCE_SCALE * 2)

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
    native = _native_renderer()
    if native is not None and getattr(native, "has_pixel_kernels", False):
        arr = np.ascontiguousarray(arr_u8, dtype=np.uint8)
        result = np.empty(arr.shape[:2], np.float32)
        native.lib.carto_luminance_rgb(arr.ctypes.data, result.ctypes.data, result.size)
        return result
    return (
        0.299 * arr_u8[..., 0]
        + 0.587 * arr_u8[..., 1]
        + 0.114 * arr_u8[..., 2]
    ).astype(np.float32) / 255.0

class _Overlay:
    """A translucent layer resampled onto a backend's pixel grid.

    Held apart from the base image so its brightness reaches the *colour* of a
    cell without reaching the tone statistics that pick the cell's glyph.
    """

    __slots__ = ("rgb", "alpha", "lum")

    def __init__(self, rgb: np.ndarray, alpha: np.ndarray, lum: np.ndarray) -> None:
        self.rgb = rgb
        self.alpha = alpha
        self.lum = lum

    def over(self, base_u8: np.ndarray) -> np.ndarray:
        """Alpha-composite onto `base_u8` -- colour output only."""
        native = _native_renderer()
        if native is not None and getattr(native, "has_pixel_kernels", False):
            base = np.ascontiguousarray(base_u8, dtype=np.uint8)
            overlay = np.ascontiguousarray(self.rgb, dtype=np.uint8)
            alpha = np.ascontiguousarray(self.alpha, dtype=np.float32)
            result = np.empty_like(base)
            native.lib.carto_blend_rgb(base.ctypes.data, overlay.ctypes.data,
                                       alpha.ctypes.data, result.ctypes.data, alpha.size)
            return result
        a = self.alpha[..., None]
        out = base_u8.astype(np.float32) * (1.0 - a) + self.rgb.astype(np.float32) * a
        return np.clip(out, 0.0, 255.0).astype(np.uint8)

def _prep_overlay(
    overlay: Optional[Image.Image], tw: int, th: int
) -> Optional[_Overlay]:
    if overlay is None:
        return None
    try:
        if overlay.mode != "RGBA":
            overlay = overlay.convert("RGBA")
        a = np.asarray(_resample(overlay, tw, th), dtype=np.uint8)
        if a.ndim != 3 or a.shape[-1] != 4:
            return None
        return _Overlay(a[..., :3], a[..., 3].astype(np.float32) / 255.0,
                        _luminance(a[..., :3]))
    except Exception:
        return None

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

_FG_CACHE_MAX = 65536
_HB_CACHE_MAX = 200000

def _fg_style(v: int) -> str:
    s = _FG_CACHE.get(v)
    if s is None:
        s = f"fg:#{v:06x}"
        if len(_FG_CACHE) >= _FG_CACHE_MAX:
            _FG_CACHE.clear()
        _FG_CACHE[v] = s
    return s

def _glyph_text(codes: np.ndarray) -> str:
    """Flatten codepoints or single-char cells to one str, at C speed.

    `codes` is either an integer array of codepoints or a numpy "<U1" array.
    Both are UCS-4 under the hood, so a single tobytes/decode replaces a
    per-character chr() loop -- which at 240x67 is 16k Python calls per frame.
    """
    if codes.dtype.kind == "U":
        buf = np.ascontiguousarray(codes)
    else:
        buf = np.ascontiguousarray(codes, dtype="<u4")
    return buf.tobytes().decode("utf-32-le")

def _pack_rgb(rgb: np.ndarray) -> np.ndarray:
    return ((rgb[:, 0].astype(np.int32) << 16)
            | (rgb[:, 1].astype(np.int32) << 8)
            | rgb[:, 2])

def _emit_row_color_fast(
    row: str,
    rgb: np.ndarray,
) -> LineFrag:
    return _emit_row_packed(row, _pack_rgb(rgb))

def _emit_row_packed(row: str, packed: np.ndarray) -> LineFrag:
    w = packed.shape[0]
    if w == 0:
        return [("", "")]
    diff = np.empty(w, dtype=bool)
    diff[0] = True
    np.not_equal(packed[1:], packed[:-1], out=diff[1:])
    starts = np.flatnonzero(diff)
    # Gather run keys in one vectorised hop: indexing `packed` inside the loop
    # would build a numpy scalar per run, which costs more than the rest of it.
    keys = packed[starts].tolist()
    s_list = starts.tolist()
    e_list = s_list[1:]
    e_list.append(w)
    get = _FG_CACHE.get
    out: LineFrag = []
    ap = out.append
    for k, s, e in zip(keys, s_list, e_list):
        st = get(k)
        if st is None:
            st = _fg_style(k)
        ap((st, row[s:e]))
    return out

# --------------------------------------------------------------- native cells

_NATIVE_MODES = {"ascii": 0, "quadrant": 1, "braille": 2, "half": 3}
_native_state = {"checked": False, "renderer": None}

def _native_renderer():
    """The libcarto handle, if it is present and new enough to cellify."""
    st = _native_state
    if not st["checked"]:
        st["checked"] = True
        try:
            from cartotui.rendering.libcarto_backend import _get_renderer
            r = _get_renderer()
            st["renderer"] = r if getattr(r, "has_cells", False) else None
        except Exception:
            st["renderer"] = None
    return st["renderer"]

def _thresh_params(mode: str, percentile: float):
    """(threshold_mode, black_pct, white_pct), mirroring threshold._params_for.

    Returns None for anything the native path does not implement, which sends
    the caller back to the Python backends.
    """
    if mode == "adaptive":
        return 0, 8.0, 96.0
    if mode == "fixed":
        return 1, 0.0, 100.0
    if mode == "percentile":
        return 1, 8.0, float(np.clip(40.0 + percentile, 80.0, 99.0))
    if mode == "stable":
        return 3, 0.0, 100.0
    if mode == "edge":
        return None          # needs the sobel pass; not worth duplicating
    return 1, 8.0, 96.0

def _native_cells(img, term_w, term_h, use_color, mode, palette,
                  orientation, threshold_mode, percentile, shaded, packed=False):
    """Reduce an image to cells in C. Returns None if the fast path cannot run."""
    r = _native_renderer()
    if r is None:
        return None
    if mode == "braille" and use_color and not shaded and not hasattr(r.lib, "carto_color_braille_version"):
        return None
    if mode == "braille" and not shaded and not hasattr(r.lib, "carto_pure_braille_version"):
        return None
    if threshold_mode == "stable" and mode != "half" and not getattr(r, "has_stable_cells", False):
        return None
    # Direct colour encoders need no luminance threshold analysis.
    direct_color = mode == "half" or (mode == "braille" and use_color and not shaded)
    params = _thresh_params("fixed" if direct_color else threshold_mode, percentile)
    if params is None:
        return None
    thresh, black_pct, white_pct = params

    import carto_ffi

    kind = _NATIVE_MODES[mode]
    cw, chh = (1, 1) if mode == "ascii" else (
        (2, 2) if mode == "quadrant" else ((2, 4) if mode == "braille" else (1, 2)))
    tw, th = term_w * cw, term_h * chh

    native_src = None
    from cartotui.rendering.libcarto_backend import NativeFrame
    if isinstance(img, NativeFrame) and r.has_cells_565:
        native_src = img
        arr = None
    else:
        if isinstance(img, NativeFrame):
            img = img.image()
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width != tw or img.height != th:
            img = _resample(img, tw, th)
        arr = np.ascontiguousarray(np.asarray(img, dtype=np.uint8))
        if arr.ndim != 3 or arr.shape[2] != 3:
            return None

    chars = list(palette) if palette else list(" .") if mode == "ascii" else list(" ░▒▓█")
    if len(chars) < 2:
        chars = list(" .")
    levels = len(chars) if mode == "ascii" else max(2, len(chars))
    pal = np.array([ord(c) for c in chars[:levels]], dtype=np.uint32)

    orient = {"dark": 0, "bright": 1}.get(orientation, 2)
    opts = carto_ffi.CartoCellOpts(
        mode=kind, cols=term_w, rows=term_h,
        mono=0 if use_color else 1,
        want_color=1 if (use_color or mode == "half") else 0,
        orientation=orient, threshold_mode=thresh,
        black_pct=black_pct, white_pct=white_pct,
        tile_grid=4, signal_floor=0.06, signal_gamma=1.2,
        shaded=1 if shaded else 0,
        palette_len=int(pal.size),
        palette=pal.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
    )

    n = term_w * term_h
    glyph = np.empty(n, dtype=np.uint32)
    want_color = bool(opts.want_color)
    fg = np.empty(n, dtype=np.uint32) if want_color else None
    bg = np.empty(n, dtype=np.uint32) if mode == "half" or (mode == "braille" and use_color and not shaded) else None
    fgp = fg.ctypes.data if fg is not None else 0
    bgp = bg.ctypes.data if bg is not None else 0
    try:
        if native_src is not None:
            ok = r.cellify_rgb565(native_src.indices.ctypes.data,
                                  native_src.width, native_src.height,
                                  native_src.lut32.ctypes.data, opts,
                                  glyph.ctypes.data, fgp, bgp)
            if not ok:
                return None
        else:
            r.cellify(arr.ctypes.data, tw, th, opts, glyph.ctypes.data, fgp, bgp)
    except Exception as e:
        log.debug("carto_cellify failed (%s); using the python backend", e)
        return None

    if packed:
        from cartotui.rendering.packed import PackedFrame
        return PackedFrame(glyph, fg, bg, term_w, term_h)
    text = _glyph_text(glyph)
    frame: FrameFrag = []
    if bg is not None:
        fg2 = fg.reshape(term_h, term_w)
        bg2 = bg.reshape(term_h, term_w)
        for y in range(term_h):
            off = y * term_w
            frame.append(_emit_halfblock_packed(text[off:off + term_w],
                                                fg2[y], bg2[y]))
    elif want_color:
        fg2 = fg.reshape(term_h, term_w).astype(np.int32, copy=False)
        for y in range(term_h):
            off = y * term_w
            frame.append(_emit_row_packed(text[off:off + term_w], fg2[y]))
    else:
        for y in range(term_h):
            off = y * term_w
            frame.append([("", text[off:off + term_w])])
    return frame

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
        overlay: Optional[Image.Image] = None,
        orientation: Optional[str] = None,
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width != term_w or img.height != term_h:
            img = _resample(img, term_w, term_h)

        arr = np.asarray(img, dtype=np.uint8)
        lum = _luminance(arr)
        ov = _prep_overlay(overlay, term_w, term_h)
        glyph_chars = list(palette) if palette else list(" .")
        levels = len(glyph_chars)
        if dither and dither != "none":
            from cartotui.rendering.threshold import _blend_overlay, estimate_orientation
            orient = orientation if orientation in ("dark", "bright") else estimate_orientation(lum)
            flip_lum = lum if orient == "dark" else (1.0 - lum)
            if ov is not None:
                flip_lum = _blend_overlay(flip_lum, ov.lum, ov.alpha)
            idx = _quantize(flip_lum, levels, dither)
        else:
            idx = compute_fill_levels(
                lum, levels,
                threshold_mode=self.threshold_mode,
                percentile=self.percentile,
                overlay_lum=None if ov is None else ov.lum,
                overlay_alpha=None if ov is None else ov.alpha,
                orientation=orientation,
            )
        if ov is not None:
            arr = ov.over(arr)
        glyphs_arr = np.array(glyph_chars)

        text = _glyph_text(glyphs_arr[idx])
        frame: FrameFrag = []
        if use_color:
            for y in range(term_h):
                off = y * term_w
                frame.append(
                    _emit_row_color_fast(text[off:off + term_w], arr[y]))
        else:
            for y in range(term_h):
                off = y * term_w
                frame.append([("", text[off:off + term_w])])
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
        overlay: Optional[Image.Image] = None,
        orientation: Optional[str] = None,
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
        ov = _prep_overlay(overlay, target_w, target_h)

        palette_chars = list(palette) if palette else list(" ░▒▓█")
        levels = max(2, len(palette_chars))
        fill = compute_fill_levels(
            lum, 256 if self.threshold_mode == "stable" else levels,
            threshold_mode=self.threshold_mode,
            percentile=self.percentile,
            overlay_lum=None if ov is None else ov.lum,
            overlay_alpha=None if ov is None else ov.alpha,
            orientation=orientation,
        )
        if ov is not None:
            arr = ov.over(arr)

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

        if self.threshold_mode == "stable":
            # Decide coverage before reducing to a display palette. A per-cell
            # mean turns even tiny differences into arbitrary quadrant shapes.
            codes = (((tl >= 80) << 3) | ((tr >= 80) << 2)
                     | ((bl >= 80) << 1) | (br >= 80)).astype(np.uint8)
            cell_avg = np.rint(cell_avg * ((levels - 1) / 255.0)).astype(np.int32)
            cell_max = np.rint(cell_max * ((levels - 1) / 255.0)).astype(np.int32)
            cell_min = np.rint(cell_min * ((levels - 1) / 255.0)).astype(np.int32)

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

        text = _glyph_text(cell_glyphs)
        frame: FrameFrag = []
        for y in range(term_h):
            off = y * term_w
            row = text[off:off + term_w]
            if use_color:
                frame.append(_emit_row_color_fast(row, cell_rgb[y]))
            else:
                frame.append([("", row)])
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

def _color_braille(arr, term_w, term_h):
    """Fit each 2x4 sample to two RGB colours; dots encode real detail.

    Flat fills get a blank cell with their actual background colour. Unlike
    density glyphs, this never invents dots across uniform land or water.
    Integer means and deterministic ties match the portable C implementation.
    """
    from cartotui.rendering.packed import PackedFrame
    p = arr.reshape(term_h, 4, term_w, 2, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 8, 3).astype(np.int32)
    spread = p.max(1) - p.min(1)
    channel = spread.argmax(1)
    v = np.take_along_axis(p, channel[:, None, None], 2)[..., 0]
    idx = np.arange(len(p))
    low, high = p[idx, v.argmin(1)], p[idx, v.argmax(1)]
    for _ in range(2):
        mask = ((p-high[:, None])**2).sum(2) < ((p-low[:, None])**2).sum(2)
        n = mask.sum(1)
        high = (p*mask[..., None]).sum(1) // np.maximum(n, 1)[:, None]
        low = (p*~mask[..., None]).sum(1) // np.maximum(8-n, 1)[:, None]
    swap = n > 4
    fg = np.where(swap[:, None], low, high)
    bg = np.where(swap[:, None], high, low)
    mask ^= swap[:, None]
    flat = spread.max(1) < 12
    bg[flat] = p[flat].sum(1) // 8
    fg[flat] = bg[flat]
    mask[flat] = False
    code = (mask*np.array([1, 8, 2, 16, 4, 32, 64, 128])).sum(1).astype(np.uint32)
    glyph = np.where(code == 0, 32, 0x2800 + code)
    return PackedFrame(glyph, _pack_rgb(fg), _pack_rgb(bg), term_w, term_h)


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
        overlay: Optional[Image.Image] = None,
        orientation: Optional[str] = None,
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
        ov = _prep_overlay(overlay, target_w, target_h)
        if use_color and not self.shaded:
            if ov is not None:
                arr = ov.over(arr)
            packed = getattr(self, "packed_output", False)
            native = (_native_cells(Image.fromarray(arr), term_w, term_h, True,
                      "braille", palette, orientation, "fixed", self.percentile,
                      False, packed=packed) if getattr(self, "native_enabled", True) else None)
            if native is not None:
                return native
            frame = _color_braille(arr, term_w, term_h)
            return frame if packed else list(frame)
        lum = _luminance(arr)

        palette_chars = list(palette) if palette else list(" ░▒▓█")
        levels = max(2, len(palette_chars))
        fill = compute_fill_levels(
            lum, 256 if self.threshold_mode == "stable" else levels,
            threshold_mode=self.threshold_mode,
            percentile=self.percentile,
            overlay_lum=None if ov is None else ov.lum,
            overlay_alpha=None if ov is None else ov.alpha,
            orientation=orientation,
        )
        if ov is not None:
            arr = ov.over(arr)

        cell_avg = fill.reshape(term_h, 4, term_w, 2).mean(axis=(1, 3))

        if self.threshold_mode == "stable":
            filled = (fill >= 80).astype(np.uint8)
            cell_avg *= (levels - 1) / 255.0
        else:
            # Broadcast the cell mean instead of allocating two repeated arrays.
            filled = (fill.reshape(term_h, 4, term_w, 2)
                      > cell_avg[:, None, :, None]).reshape(target_h, target_w).astype(np.uint8)

        codes = np.zeros((term_h, term_w), dtype=np.uint8)
        for ry in range(4):
            for cx in range(2):
                codes |= filled[ry::4, cx::2] * _BRAILLE_BITS[ry, cx]

        glyphs_int = codes.astype(np.int32) + 0x2800

        flat = (codes == 0) | (codes == 0xFF)
        palette_codes = np.array([ord(c) for c in palette_chars], dtype=np.int32)
        flat_idx = np.clip(cell_avg.astype(np.int32), 0, levels - 1)
        flat_glyphs = palette_codes[flat_idx]
        if self.shaded:
            glyphs_int = np.where(flat, flat_glyphs, glyphs_int)
        else:
            # Uniform areas still carry tone, but stay in the braille alphabet.
            density = np.clip(np.floor(cell_avg * 8 / (levels - 1) + 0.5), 0, 8).astype(np.int32)
            dots = np.array([0, 1, 129, 133, 165, 167, 231, 239, 255], np.int32)
            glyphs_int = np.where(flat, 0x2800 + dots[density], glyphs_int)

        if self.shaded and palette:
            popcount = np.unpackbits(codes[..., None], axis=-1).sum(axis=-1)
            heavy = popcount >= 6
            soft = palette_codes[np.clip(cell_avg.astype(np.int32), 1, levels - 1)]
            glyphs_int = np.where(heavy, soft, glyphs_int)

        frame: FrameFrag = []
        if use_color:
            native = _native_renderer()
            if (getattr(self, "packed_output", False) and native is not None
                    and getattr(native, "has_pixel_kernels", False)):
                from cartotui.rendering.packed import PackedFrame
                rgb = np.ascontiguousarray(arr, dtype=np.uint8)
                mask = np.ascontiguousarray(filled, dtype=np.uint8)
                fg = np.empty((term_h, term_w), np.uint32)
                native.lib.carto_braille_colors(rgb.ctypes.data, mask.ctypes.data,
                                                term_w, term_h, fg.ctypes.data)
                return PackedFrame(glyphs_int, fg, None, term_w, term_h)
            fr = filled.reshape(term_h, 4, term_w, 2).astype(np.float32)
            cnt = fr.sum(axis=(1, 3))
            inv = 1.0 / np.maximum(cnt, 1.0)

            lit_mask = cnt > 0

            def _cell_color(ch: int) -> np.ndarray:
                c = arr[..., ch].astype(np.float32).reshape(term_h, 4, term_w, 2)
                lit = (c * fr).sum(axis=(1, 3)) * inv
                whole = c.mean(axis=(1, 3))
                return np.where(lit_mask, lit, whole)

            cell_rgb = np.stack(
                [_cell_color(0), _cell_color(1), _cell_color(2)], axis=-1
            ).clip(0, 255).astype(np.uint8)
            if getattr(self, "packed_output", False):
                from cartotui.rendering.packed import PackedFrame
                c = cell_rgb.astype(np.uint32)
                fg = (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]
                return PackedFrame(glyphs_int, fg, None, term_w, term_h)
            text = _glyph_text(glyphs_int)
            for y in range(term_h):
                off = y * term_w
                frame.append(
                    _emit_row_color_fast(text[off:off + term_w], cell_rgb[y]))
        else:
            text = _glyph_text(glyphs_int)
            for y in range(term_h):
                off = y * term_w
                frame.append([("", text[off:off + term_w])])
        return frame

_UPPER_HALF = "▀"

def _emit_halfblock_packed(row: str, fgp: np.ndarray, bgp: np.ndarray) -> LineFrag:
    w = fgp.shape[0]
    if w == 0:
        return [("", "")]
    key = (fgp.astype(np.int64) << 24) | bgp
    diff = np.empty(w, dtype=bool)
    diff[0] = True
    np.not_equal(key[1:], key[:-1], out=diff[1:])
    starts = np.flatnonzero(diff)
    keys = key[starts].tolist()
    s_list = starts.tolist()
    e_list = s_list[1:]
    e_list.append(w)
    get = _HB_CACHE.get
    out: LineFrag = []
    ap = out.append
    for hk, s, e in zip(keys, s_list, e_list):
        style = get(hk)
        if style is None:
            style = f"fg:#{hk >> 24:06x} bg:#{hk & 0xFFFFFF:06x}"
            if len(_HB_CACHE) >= _HB_CACHE_MAX:
                _HB_CACHE.clear()
            _HB_CACHE[hk] = style
        ap((style, row[s:e]))
    return out

def _emit_halfblock_row(top: np.ndarray, bot: np.ndarray) -> LineFrag:
    w = top.shape[0]
    if w == 0:
        return [("", "")]
    tp = (top[:, 0].astype(np.int64) << 16) | (top[:, 1].astype(np.int64) << 8) | top[:, 2]
    bp = (bot[:, 0].astype(np.int64) << 16) | (bot[:, 1].astype(np.int64) << 8) | bot[:, 2]
    key = (tp << 24) | bp
    diff = np.empty(w, dtype=bool)
    diff[0] = True
    np.not_equal(key[1:], key[:-1], out=diff[1:])
    starts = np.flatnonzero(diff)
    keys = key[starts].tolist()
    s_list = starts.tolist()
    e_list = s_list[1:]
    e_list.append(w)
    get = _HB_CACHE.get
    out: LineFrag = []
    ap = out.append
    for hk, s, e in zip(keys, s_list, e_list):
        style = get(hk)
        if style is None:
            style = f"fg:#{hk >> 24:06x} bg:#{hk & 0xFFFFFF:06x}"
            if len(_HB_CACHE) >= _HB_CACHE_MAX:
                _HB_CACHE.clear()
            _HB_CACHE[hk] = style
        ap((style, _UPPER_HALF * (e - s)))
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
        overlay: Optional[Image.Image] = None,
        orientation: Optional[str] = None,
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]
        if img.mode != "RGB":
            img = img.convert("RGB")
        tw, th = term_w, term_h * 2
        if img.width != tw or img.height != th:
            img = _resample(img, tw, th)
        arr = np.asarray(img, dtype=np.uint8)
        ov = _prep_overlay(overlay, tw, th)
        if ov is not None:
            arr = ov.over(arr)
        if not use_color:
            g = (_luminance(arr) * 255.0).astype(np.uint8)
            arr = np.stack([g, g, g], axis=-1)
        top = arr[0::2]
        bot = arr[1::2]
        n = min(top.shape[0], bot.shape[0])
        if getattr(self, "packed_output", False):
            from cartotui.rendering.packed import PackedFrame
            def rgb24(a):
                a = a.astype(np.uint32)
                return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
            return PackedFrame(np.full((n, term_w), 0x2580, np.uint32),
                               rgb24(top[:n]), rgb24(bot[:n]), term_w, n)
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
    use_native_cells: bool = True
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
        return CELL_MAP_PX

    @staticmethod
    def subcells(mode: str) -> Tuple[int, int]:
        if mode == "quadrant":
            return 2, 2
        if mode == "braille":
            return 2, 4
        if mode == "half":
            return 1, 2
        return 1, 1

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
        overlay: Optional[Image.Image] = None,
        orientation: Optional[str] = None,
        packed: bool = False,
    ) -> FrameFrag:
        """Render `img` to terminal cells.

        `img` is the base map alone. Translucent layers (radar) belong in
        `overlay` -- an RGBA image the size of `img` -- so they tint the output
        without steering the tone mapping that chooses glyphs.

        `orientation` pins the ink polarity ("dark"/"bright"). Callers that know
        it -- a themed map does -- should pass it; otherwise it is guessed from
        the frame, and a tone-adjusted frame can guess wrong and invert.
        """
        effective_mode = self._resolve_mode(mode, source_kind)
        self.last_effective_mode = effective_mode
        key = (term_w, term_h, use_color, effective_mode, self.get_palette(palette_name),
               dither, orientation, self.subpixel_threshold, self.subpixel_percentile,
               self.shaded_blocks, self.use_native_cells)
        retained_input = img if hasattr(img, "indices") else None
        retain = packed and retained_input is not None and (
            overlay is None or getattr(overlay, "_cartotui_retained", False))
        key += (id(overlay),)
        cached = getattr(self, "_retained_cells", None)
        if retain and cached and cached[0] is img and cached[1] == key:
            return cached[2].copy()

        # libcarto does this whole reduction in one pass when nothing needs the
        # python-only extras -- a translucent overlay to composite, a dither, or
        # the edge threshold. Falls through on any miss.
        if (self.use_native_cells and overlay is None
                and (not dither or dither == "none")
                and effective_mode in _NATIVE_MODES):
            frame = _native_cells(
                img, term_w, term_h, use_color, effective_mode,
                self.get_palette(palette_name), orientation,
                self.subpixel_threshold, self.subpixel_percentile,
                self.shaded_blocks,
                packed=packed,
            )
            if frame is not None:
                if retain:
                    self._retained_cells = (img, key, frame.copy(), overlay)
                return frame

        if hasattr(img, "image"):
            img = img.image()
        backend = self._backends.get(effective_mode) or self._backends["ascii"]
        backend.packed_output = packed
        backend.native_enabled = self.use_native_cells
        frame = backend.render(
            img,
            term_w,
            term_h,
            use_color,
            self.get_palette(palette_name),
            dither,
            overlay=overlay,
            orientation=orientation,
        )
        if retain and hasattr(frame, "stamp"):
            self._retained_cells = (retained_input, key, frame.copy(), overlay)
        return frame
