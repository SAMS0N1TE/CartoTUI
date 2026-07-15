"""The native renderer has one scratch arena and one style struct for everyone.

A PNG export renders on its own thread while the map worker is still drawing, so
two threads reach libcarto at once. Both carve their carto_ctx from offset 0 of
the same arena, meaning the second carto_begin lands on the first one's context
-- c->fb included. The first thread then draws through the other's framebuffer,
and once that thread returns and Python frees its pixel buffer, the write goes
into freed memory: SIGSEGV inside carto_put_px, no Python traceback.

These tests hold the line on the serialisation that prevents it.
"""
import threading

import pytest

from cartotui.rendering.libcarto_backend import available

pytestmark = pytest.mark.skipif(not available(),
                                reason="libcarto native renderer not built")


def _renderer():
    from cartotui.rendering.libcarto_backend import _get_renderer
    return _get_renderer()


def _tile() -> bytes:
    """A minimal MVT with one road line, enough to walk the draw path."""
    def varint(v):
        out = b""
        while True:
            b_ = v & 0x7F
            v >>= 7
            out += bytes([b_ | (0x80 if v else 0)])
            if not v:
                return out

    def s(field, payload):
        return bytes([(field << 3) | 2]) + varint(len(payload)) + payload

    geom = [(1 << 3) | 1, 10, 10, (8 << 3) | 2] + [20, 14] * 8
    g = b"".join(varint(v) for v in geom)
    feat = bytes([(3 << 3) | 0]) + varint(2) + s(4, g)
    layer = (s(1, b"roads") + s(2, feat) + bytes([(5 << 3) | 0]) + varint(4096)
             + bytes([(15 << 3) | 0]) + varint(2))
    return s(3, layer)


TILE = _tile()


def test_renderer_exposes_a_reentrant_lock():
    r = _renderer()
    assert hasattr(r, "lock")
    with r.lock:
        with r.lock:
            pass


def test_render_viewport_serialises_on_that_lock():
    """If this stops holding, concurrent renders share the arena again."""
    r = _renderer()
    done = threading.Event()

    def render():
        try:
            r.render_viewport(40.75, -73.95, 9, 128, 96,
                              lambda zz, xx, yy: TILE)
        finally:
            done.set()

    with r.lock:
        t = threading.Thread(target=render, daemon=True)
        t.start()
        assert not done.wait(0.75), "render_viewport did not take the render lock"

    assert done.wait(20), "render_viewport never finished after the lock freed"
    t.join(timeout=5)


def test_concurrent_renders_do_not_corrupt_each_other():
    """Different sizes and styles at once, as export-vs-map does it."""
    from cartotui.themes import theme_vector_style

    r = _renderer()
    styles = [theme_vector_style(t, {}) for t in ("green", "night", "paper")]
    errors = []
    sizes = [(96, 64), (320, 200), (256, 160), (128, 96)]

    def work(i):
        try:
            for k in range(12):
                w, h = sizes[(i + k) % len(sizes)]
                buf, drawn = r.render_viewport(
                    40.75, -73.95, 9, w, h, lambda zz, xx, yy: TILE,
                    style=styles[(i + k) % len(styles)],
                )
                if len(buf) != w * h * 2:
                    errors.append(f"thread {i}: got {len(buf)} bytes, want {w*h*2}")
        except Exception as e:  # pragma: no cover - only on regression
            errors.append(f"thread {i}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
