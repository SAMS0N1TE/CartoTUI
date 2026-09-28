import numpy as np
import pytest
from PIL import Image

from cartotui.rendering.renderer import Renderer, default_palettes


@pytest.mark.parametrize("mode", ["ascii", "braille"])
@pytest.mark.parametrize("palette", ["shades", "hatch", "ink", "topo", "heat", "blocks", "binary"])
@pytest.mark.parametrize("threshold", ["adaptive", "stable", "fixed", "percentile", "edge"])
@pytest.mark.parametrize("native", [False, True])
def test_unshaded_character_modes_never_emit_blocks(mode, palette, threshold, native):
    # Broad fills, gradients and narrow details exercise both flat-cell fallback
    # and partial coverage, independent of the source zoom or palette length.
    a = np.tile(np.arange(256, dtype=np.uint8), (64, 1))
    a[12:16] = 240
    a[::4, ::2] = 0
    a[1::4, ::2] = 255
    img = Image.fromarray(np.repeat(a[..., None], 3, axis=2))
    r = Renderer(default_palettes(), subpixel_threshold=threshold, use_native_cells=native)
    rows = r.render(img, 128, 16, True, mode, palette_name=palette, packed=True)
    chars = [ch for row in rows for _, text in row for ch in text]
    assert not any(0x2580 <= ord(ch) <= 0x259f for ch in chars)
    assert any(ch not in (" ", "\u2800") for ch in chars)


def test_shading_explicitly_restores_block_palette():
    img = Image.fromarray(np.repeat(np.tile(np.arange(256, dtype=np.uint8), (32, 1))[..., None], 3, axis=2))
    r = Renderer(default_palettes(), shaded_blocks=True)
    rows = r.render(img, 128, 8, True, "ascii", palette_name="shades")
    assert any(0x2580 <= ord(ch) <= 0x259f for row in rows for _, text in row for ch in text)
