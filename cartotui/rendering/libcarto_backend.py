from __future__ import annotations

import gzip
import logging
import os
import sys

log = logging.getLogger("cartotui.libcarto")

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
            log.warning("libcarto unavailable (%s); build libcarto/build/carto.dll", e)
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


def _rgb565_to_image(rgb565: bytes, w: int, h: int):
    import numpy as np
    from PIL import Image
    v = np.frombuffer(rgb565, dtype="<u2").reshape(h, w).astype(np.uint32)
    r = ((v >> 11) & 0x1F) * 255 // 31
    g = ((v >> 5) & 0x3F) * 255 // 63
    b = (v & 0x1F) * 255 // 31
    rgb = np.dstack([r, g, b]).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def rasterise_view_libcarto(vector_source, lat, lon, z, px_w, px_h, style=None):
    renderer = _get_renderer()

    def fetch(zz, xx, yy):
        raw = vector_source._fetch_raw(zz, xx, yy)
        if raw and raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        return raw

    rgb565, drawn = renderer.render_viewport(lat, lon, z, px_w, px_h, fetch)
    if drawn == 0:
        return None
    return _rgb565_to_image(rgb565, px_w, px_h)
