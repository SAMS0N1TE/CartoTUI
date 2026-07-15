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

def _rgb565_to_image(rgb565: bytes, w: int, h: int):
    import numpy as np
    from PIL import Image
    v = np.frombuffer(rgb565, dtype="<u2").reshape(h, w)
    rgb = _rgb565_lut()[v]
    return Image.fromarray(rgb, "RGB")

def rasterise_view_libcarto(vector_source, lat, lon, z, px_w, px_h, style=None,
                            preload=False, cached_only=False, supersample=1.0,
                            road_thickness=1.0):
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

    rgb565, drawn = renderer.render_viewport(
        lat, lon, z, px_w, px_h, counted_fetch,
        style=style,
        road_width_scale=(max(1.0, float(supersample))
                          * max(0.05, float(road_thickness))),
    )
    if preload:
        renderer.prefetch_ring(lat, lon, z, px_w, px_h, base_fetch, ring=1)
    if drawn == 0:
        return None
    return _rgb565_to_image(rgb565, px_w, px_h)
