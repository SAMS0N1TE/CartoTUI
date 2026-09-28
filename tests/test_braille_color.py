import numpy as np
import pytest
from PIL import Image

from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.rendering.packed import DEFAULT


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("background", [(12, 15, 20), (239, 230, 205), (90, 120, 70)])
def test_uniform_braille_inherits_terminal_background(native, background):
    r = Renderer(default_palettes(), use_native_cells=native)
    image = Image.new("RGB", (40, 40), background)
    frame = r.render(image, 20, 10, True, "braille", packed=True)
    assert np.all(frame.bg == DEFAULT)
    assert set(map(chr, frame.glyph.flat)) <= set(default_palettes()["dos5"])


@pytest.mark.parametrize("native", [False, True])
def test_colour_braille_honours_palette_and_threshold(native):
    r = Renderer(default_palettes(), use_native_cells=native)
    a = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 3, axis=2)
    image = Image.fromarray(np.repeat(a, 32, axis=0))
    def glyphs(palette):
        rows = r.render(image, 128, 8, True, "braille", palette_name=palette, orientation="dark")
        return "".join(text for row in rows for _, text in row)
    original = glyphs("dos5")
    assert original != glyphs("hatch")
    r.update_options(subpixel_threshold="stable")
    assert original != glyphs("dos5")


def test_native_and_portable_braille_agree_with_radar():
    image = Image.fromarray(np.random.default_rng(12).integers(0, 256, (80, 80, 3), dtype=np.uint8))
    overlay = Image.new("RGBA", image.size, (0, 180, 240, 130))
    r = Renderer(default_palettes(), use_native_cells=True)
    native = r.render(image, 40, 20, True, "braille", overlay=overlay, packed=True)
    r.use_native_cells = False
    portable = r.render(image, 40, 20, True, "braille", overlay=overlay, packed=True)
    for field in ("glyph", "fg", "bg"):
        np.testing.assert_array_equal(getattr(native, field), getattr(portable, field))
