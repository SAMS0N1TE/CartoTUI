import numpy as np
import pytest

from cartotui.rendering.packed import DEFAULT, PackedFrame
from cartotui.rendering.text_contrast import balance_dos_ink
from cartotui.themes import available_themes, theme_vector_style
from cartotui.ui.solid_geometry import luminance


@pytest.mark.parametrize('theme', available_themes())
def test_dos_ink_is_legible_without_changing_texture(theme):
    style = theme_vector_style(theme)
    rgb = np.array([style.water, style.park, style.building, style.road_color], np.uint32)
    fg = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    glyph = np.array([[ord(c) for c in '.:+#']], np.uint32)
    frame = PackedFrame(glyph, fg, None, 4, 1)
    before_bg = frame.bg.copy()
    result = balance_dos_ink(frame, style.bg)
    np.testing.assert_array_equal(result.glyph, glyph)
    np.testing.assert_array_equal(result.bg, before_bg)
    values = result.fg
    colors = np.stack(((values >> 16) & 255, (values >> 8) & 255, values & 255), -1)
    lum, bg = luminance(colors), luminance(style.bg)
    ratio = (np.maximum(lum, bg) + .05) / (np.minimum(lum, bg) + .05)
    assert (ratio >= 4.45).all()  # integer RGB rounding tolerance


def test_fragment_and_packed_ink_match_and_keep_explicit_background():
    packed = PackedFrame([[ord('.')]], [[0x304060]], [[0x112233]], 1, 1)
    packed = balance_dos_ink(packed, (12, 12, 12))
    fragments = balance_dos_ink([[('fg:#304060 bg:#112233 bold', '.')]], (12, 12, 12))
    assert fragments == [[(f'fg:#{packed.fg[0, 0]:06x} bg:#112233 bold', '.')]]
    assert packed.bg[0, 0] == 0x112233
    default = PackedFrame([[32]], [[DEFAULT]], None, 1, 1)
    assert balance_dos_ink(default, (240, 240, 240)).fg[0, 0] == DEFAULT
