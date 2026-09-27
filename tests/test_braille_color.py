import numpy as np
import pytest
from PIL import Image

from cartotui.rendering.renderer import Renderer, default_palettes


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("background", [(12, 15, 20), (239, 230, 205), (90, 120, 70)])
def test_uniform_braille_has_no_dot_wall(native, background):
    r = Renderer(default_palettes(), use_native_cells=native)
    image = Image.new("RGB", (40, 40), background)
    frame = r.render(image, 20, 10, True, "braille", packed=True)
    assert np.all(frame.glyph == 32)
    color = (background[0] << 16) | (background[1] << 8) | background[2]
    assert np.all(frame.bg == color)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("background,ink", [((10, 20, 30), (240, 210, 100)),
                                           ((240, 230, 210), (20, 40, 80)),
                                           ((0, 100, 0), (200, 0, 0))])
def test_single_subcell_detail_survives_on_dark_light_and_equal_luminance(native, background, ink):
    r = Renderer(default_palettes(), use_native_cells=native)
    image = Image.new("RGB", (2, 4), background)
    image.putpixel((1, 2), ink)
    frame = r.render(image, 1, 1, True, "braille", packed=True)
    assert frame.glyph[0, 0] == 0x2820
    assert frame.fg[0, 0] == (ink[0] << 16) | (ink[1] << 8) | ink[2]
    assert frame.bg[0, 0] == (background[0] << 16) | (background[1] << 8) | background[2]


def test_native_and_portable_braille_agree_with_radar():
    image = Image.fromarray(np.random.default_rng(12).integers(0, 256, (80, 80, 3), dtype=np.uint8))
    overlay = Image.new("RGBA", image.size, (0, 180, 240, 130))
    r = Renderer(default_palettes(), use_native_cells=True)
    native = r.render(image, 40, 20, True, "braille", overlay=overlay, packed=True)
    r.use_native_cells = False
    portable = r.render(image, 40, 20, True, "braille", overlay=overlay, packed=True)
    for field in ("glyph", "fg", "bg"):
        np.testing.assert_array_equal(getattr(native, field), getattr(portable, field))
