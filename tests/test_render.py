import numpy as np
from PIL import Image

from cartotui.rendering.libcarto_backend import _rgb565_lut, _rgb565_to_image
from cartotui.rendering.renderer import Renderer, _resample, default_palettes


def _img(w=720, h=600):
    a = (np.random.RandomState(0).rand(h, w, 3) * 255).astype(np.uint8)
    return Image.fromarray(a, "RGB")


def test_render_modes_dims():
    r = Renderer(default_palettes())
    img = _img()
    for mode in ("ascii", "half", "quadrant", "braille"):
        rows = r.render(img, 120, 50, True, mode=mode)
        assert len(rows) == 50
        assert sum(len(t) for _, t in rows[0]) == 120


def test_render_mono():
    r = Renderer(default_palettes())
    rows = r.render(_img(), 80, 24, False, mode="ascii")
    assert len(rows) == 24


def test_rgb565_lut_matches_formula():
    lut = _rgb565_lut()
    for v in (0, 0x07E0, 0xF800, 0x001F, 0xFFFF, 0x1234):
        r = ((v >> 11) & 0x1F) * 255 // 31
        g = ((v >> 5) & 0x3F) * 255 // 63
        b = (v & 0x1F) * 255 // 31
        assert tuple(lut[v]) == (r, g, b)


def test_rgb565_to_image():
    buf = bytes([0x00, 0xF8] * (4 * 4))  # 0xF800 = pure red
    im = _rgb565_to_image(buf, 4, 4)
    assert im.size == (4, 4)
    assert im.getpixel((0, 0)) == (255, 0, 0)


def test_resample_exact_integer_uses_reduce():
    img = _img(720, 600)
    out = _resample(img, 120, 50)
    assert out.size == (120, 50)


def test_resample_noninteger():
    img = _img(700, 500)
    out = _resample(img, 120, 50)
    assert out.size == (120, 50)
