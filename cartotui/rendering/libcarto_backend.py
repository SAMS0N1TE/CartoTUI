from __future__ import annotations

import gzip
import logging
import os
import sys
import threading

log = logging.getLogger("cartotui.libcarto")

_load_lock = threading.Lock()
_load_pending = 0

def get_loading() -> int:
    with _load_lock:
        return _load_pending

_BINDINGS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "bindings", "python")
)
if _BINDINGS not in sys.path:
    sys.path.insert(0, _BINDINGS)

_renderer = None
_unavailable = False

def _get_renderer():
    global _renderer, _unavailable
    if _renderer is None and not _unavailable:
        try:
            from carto_ffi import Renderer
            _renderer = Renderer()
        except Exception as e:
            _unavailable = True
            _libname = {"win32": "carto.dll", "darwin": "libcarto.dylib"}.get(
                sys.platform, "libcarto.so")
            log.warning(
                "libcarto native renderer unavailable (%s); using the pure-Python "
                "renderer. To build it: cmake -S libcarto -B libcarto/build && "
                "cmake --build libcarto/build  (produces %s).", e, _libname)
            raise
    if _renderer is None:
        raise RuntimeError("libcarto renderer unavailable")
    return _renderer

def available() -> bool:
    try:
        _get_renderer()
        return True
    except Exception:
        return False

_RGB565_LUT = None

def _rgb565_lut():
    global _RGB565_LUT
    if _RGB565_LUT is None:
        import numpy as np
        v = np.arange(65536, dtype=np.uint32)
        r = (((v >> 11) & 0x1F) * 255 // 31).astype(np.uint8)
        g = (((v >> 5) & 0x3F) * 255 // 63).astype(np.uint8)
        b = ((v & 0x1F) * 255 // 31).astype(np.uint8)
        _RGB565_LUT = np.stack([r, g, b], axis=1)
    return _RGB565_LUT

_LUM565 = None

def _lum565():
    """Luminance of every RGB565 colour, matching composite's _LUMA weights."""
    global _LUM565
    if _LUM565 is None:
        import numpy as np
        from cartotui.composite import _LUMA
        _LUM565 = (_rgb565_lut().astype(np.float32) / 255.0) @ _LUMA
    return _LUM565

def _toned_lut(pivot: float, tone: dict):
    """The RGB565 table with the tone chain already applied.

    libcarto hands back RGB565, so a frame holds at most 65536 distinct colours
    however many pixels it has. Toning the table and then looking up is the same
    arithmetic on the same values as toning every pixel, for a twentieth of the
    work -- and it costs nothing extra at lookup time, because the frame is
    gathered through this table either way.
    """
    from cartotui.composite import tone_colors
    return tone_colors(_rgb565_lut(), pivot, **tone)

def _pack_lut32(lut):
    """Pack an (N,3) uint8 table into little-endian RGBA words.

    Gathering one 4-byte word per pixel is several times quicker than gathering
    a 3-byte row, and the result reads straight back as an RGBA buffer.
    """
    import numpy as np
    return ((lut[:, 0].astype(np.uint32)
             | (lut[:, 1].astype(np.uint32) << 8)
             | (lut[:, 2].astype(np.uint32) << 16)
             | np.uint32(0xFF000000)).astype("<u4"))

_BASE_LUT32 = None
_TONED_LUT32 = None  # (cache key, packed lut)

class NativeFrame:
    """A rendered framebuffer that has not been turned into pixels yet.

    Materialising the RGB image costs a 65k-entry gather over a million pixels
    and then a PIL resample down to the cell grid. When the renderer is going
    straight to terminal cells libcarto can do both itself, and neither is
    needed -- so hold the raw buffer and only convert if something asks.
    """

    __slots__ = ("indices", "width", "height", "lut32", "_image")
    mode = "RGB"

    def __init__(self, indices, width, height, lut32):
        self.indices = indices
        self.width = int(width)
        self.height = int(height)
        self.lut32 = lut32
        self._image = None

    @property
    def size(self):
        return (self.width, self.height)

    def image(self):
        if self._image is None:
            self._image = _image_from(self.indices, self.width, self.height,
                                      self.lut32)
        return self._image

    def convert(self, mode):
        img = self.image()
        return img if img.mode == mode else img.convert(mode)


def _image_from(v, w, h, lut32):
    from PIL import Image
    out32 = lut32[v]
    return Image.frombuffer("RGBA", (w, h), out32, "raw", "RGBA", 0, 1).convert("RGB")


def _lut_for(v, tone):
    """The colour table this frame should be gathered through."""
    global _BASE_LUT32, _TONED_LUT32
    import numpy as np

    lut32 = None
    if tone:
        # The pivot is the frame's mean luminance, taken off a 65536-bin
        # histogram of the colour indices rather than off the pixels: the same
        # sum, without materialising a float image to reduce.
        counts = np.bincount(v.ravel(), minlength=65536)
        total = int(counts.sum())
        if total:
            pivot = float((counts * _lum565()).sum() / total)
            key = (pivot, tuple(sorted(tone.items())))
            cached = _TONED_LUT32
            if cached is not None and cached[0] == key:
                lut32 = cached[1]
            else:
                lut32 = _pack_lut32(_toned_lut(pivot, tone))
                _TONED_LUT32 = (key, lut32)
    if lut32 is None:
        if _BASE_LUT32 is None:
            _BASE_LUT32 = _pack_lut32(_rgb565_lut())
        lut32 = _BASE_LUT32
    return lut32


def _rgb565_to_image(rgb565: bytes, w: int, h: int, tone: dict = None):
    import numpy as np
    v = np.frombuffer(rgb565, dtype="<u2").reshape(h, w)
    return _image_from(v, w, h, _lut_for(v, tone))

def rasterise_view_libcarto(vector_source, lat, lon, z, px_w, px_h, style=None,
                            preload=False, cached_only=False, supersample=1.0,
                            road_thickness=1.0, tone=None, max_fetch_zoom=None,
                            lazy=False):
    renderer = _get_renderer()

    def base_fetch(zz, xx, yy):
        raw = vector_source.get_raw(zz, xx, yy, cached_only=cached_only)
        if raw and raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        return raw

    def counted_fetch(zz, xx, yy):
        global _load_pending
        with _load_lock:
            _load_pending += 1
        try:
            return base_fetch(zz, xx, yy)
        finally:
            with _load_lock:
                _load_pending -= 1

    fetch_z = z if max_fetch_zoom is None else min(int(z), int(max_fetch_zoom))
    rgb565, drawn = renderer.render_viewport(
        lat, lon, z, px_w, px_h, counted_fetch,
        style=style,
        road_width_scale=(max(1.0, float(supersample))
                          * max(0.05, float(road_thickness))),
        fetch_z=fetch_z,
    )
    if preload:
        renderer.prefetch_ring(lat, lon, fetch_z, px_w, px_h, base_fetch, ring=1)
    if drawn == 0:
        return None
    if lazy:
        import numpy as np
        v = np.frombuffer(rgb565, dtype="<u2").reshape(px_h, px_w)
        return NativeFrame(v, px_w, px_h, _lut_for(v, tone))
    return _rgb565_to_image(rgb565, px_w, px_h, tone)
