"""A translucent overlay must tint the map without steering its tone mapping.

Radar used to be pasted into the image before thresholding, which let bright
precipitation set the white point for the whole viewport: the map underneath --
open ocean worst of all -- got crushed to the blank glyph, i.e. black holes.
"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.rendering.threshold import compute_binary_fill, compute_fill_levels

W, H = 240, 120
FAR = 0.60
MODES = ("adaptive", "edge", "percentile", "fixed")


def _scene():
    """Dark water with a landmass on the left -- the case that broke."""
    img = Image.new("RGB", (W, H), (36, 58, 110))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 0), (int(W * 0.34), 0), (int(W * 0.28), H), (0, H)], fill=(0, 0, 0))
    d.rectangle([10, 20, 60, 50], fill=(48, 49, 58))
    d.line([(5, 70), (70, 95)], fill=(224, 30, 30), width=2)
    return img


def _radar():
    """Concentric precipitation, bright against the map, centred over water."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy, r = int(W * 0.42), int(H * 0.5), 34
    for i, col in enumerate([(20, 200, 40, 255), (240, 230, 40, 255), (230, 40, 30, 255)]):
        rr = r * (1.0 - i * 0.3)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)
    layer.putalpha(layer.getchannel("A").point(lambda a: int(a * 0.65)))
    return layer


def _glyphs(rows):
    return [[c for _, t in row for c in t] for row in rows]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("render_mode", ("ascii", "quadrant", "braille"))
def test_overlay_leaves_distant_map_untouched(mode, render_mode):
    r = Renderer(default_palettes(), subpixel_threshold=mode)
    kw = dict(mode=render_mode, palette_name="shades")
    plain = _glyphs(r.render(_scene(), 60, 15, False, **kw))
    tinted = _glyphs(r.render(_scene(), 60, 15, False, overlay=_radar(), **kw))

    col = int(60 * FAR)
    for y, (a, b) in enumerate(zip(plain, tinted)):
        assert a[col:] == b[col:], (
            f"{mode}/{render_mode}: radar changed the map {FAR:.0%} away on row {y}"
        )


def test_overlay_alpha_zero_is_a_noop():
    lum = np.asarray(_scene().convert("L"), dtype=np.float32) / 255.0
    zeros = np.zeros_like(lum)
    base = compute_fill_levels(lum, 5)
    with_empty = compute_fill_levels(lum, 5, overlay_lum=zeros, overlay_alpha=zeros)
    assert np.array_equal(base, with_empty)


def test_overlay_keeps_its_own_gradation_in_mono():
    """Light and heavy precipitation have to stay apart where the glyph is the
    only channel carrying intensity."""
    lum = np.full((40, 40), 0.05, dtype=np.float32)
    alpha = np.ones_like(lum)
    grad = np.tile(np.linspace(0.3, 1.0, 40, dtype=np.float32), (40, 1))
    fill = compute_fill_levels(lum, 5, overlay_lum=grad, overlay_alpha=alpha)
    assert len(np.unique(fill)) >= 3, "overlay collapsed to a single flat level"
    assert fill[:, 0].mean() < fill[:, -1].mean(), "gradation runs the wrong way"


def test_faint_overlay_is_still_visible():
    """The floor exists so the lightest precipitation cannot quantise away."""
    lum = np.zeros((20, 20), dtype=np.float32)
    faint = np.full_like(lum, 0.02)
    fill = compute_fill_levels(lum, 5, overlay_lum=faint,
                               overlay_alpha=np.ones_like(lum))
    assert fill.min() >= 1, "faint overlay vanished into the blank glyph"


def test_overlay_tints_colour_output():
    r = Renderer(default_palettes())
    styles = [s for row in r.render(_scene(), 60, 15, True, mode="quadrant",
                                    overlay=_radar()) for s, _ in row]
    assert any(s for s in styles), "overlay produced no colour at all"


def test_binary_fill_accepts_an_overlay():
    lum = np.asarray(_scene().convert("L"), dtype=np.float32) / 255.0
    alpha = np.zeros_like(lum)
    alpha[40:80, 40:80] = 1.0
    out = compute_binary_fill(lum, overlay_lum=np.ones_like(lum), overlay_alpha=alpha)
    assert out.shape == lum.shape
    assert out[40:80, 40:80].mean() > 0.9, "opaque bright overlay should read as on"


def test_half_block_backend_accepts_an_overlay():
    r = Renderer(default_palettes())
    rows = r.render(_scene(), 40, 10, True, mode="half", overlay=_radar())
    assert len(rows) == 10
