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


def _paper_scene():
    """Ink-on-paper: dark features on a light ground."""
    a = np.full((80, 120, 3), 235, dtype=np.uint8)
    a[20:30, 10:60] = 90
    a[45:60, 30:100] = 60
    return Image.fromarray(a, "RGB")


def _ink(img, orientation):
    """Mean fill on the dark features vs the light ground."""
    from cartotui.rendering.threshold import compute_fill_levels

    lum = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    fill = compute_fill_levels(lum, 5, orientation=orientation)
    return float(fill[45:60, 30:100].mean()), float(fill[0:15, 0:120].mean())


def test_pinned_orientation_survives_a_darkened_frame():
    """Darkening a light theme far enough drags its mean luminance under the
    auto-detect threshold, which flips the glyph ramp and inverts the map. A
    pinned polarity has to hold so the tone knobs stay continuous -- tone may
    change how much ink lands, never which side of the map gets it."""
    from cartotui.composite import apply_image_adjustments

    base = _paper_scene()
    for wp in (1.0, 0.8, 0.6, 0.5, 0.4):
        feature, ground = _ink(apply_image_adjustments(base, white_point=wp), "bright")
        assert feature > ground, f"white_point {wp} inverted the map"


def test_unpinned_orientation_inverts_when_darkened():
    """Why the pin exists: left to guess, the same slide flips polarity."""
    from cartotui.composite import apply_image_adjustments

    base = _paper_scene()
    assert _ink(base, None)[0] > _ink(base, None)[1]
    feature, ground = _ink(apply_image_adjustments(base, white_point=0.4), None)
    assert feature < ground, "expected the auto-detect fallback to invert here"


def test_orientation_is_guessed_when_not_pinned():
    """The fallback still works for sources with no theme polarity (raster)."""
    r = Renderer(default_palettes())
    rows = r.render(_paper_scene(), 40, 10, False, mode="ascii", palette_name="shades")
    assert len(rows) == 10
