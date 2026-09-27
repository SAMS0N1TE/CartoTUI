import numpy as np

from cartotui.rendering.libcarto_backend import _lum565, _lut_for, _rgb565_to_image


def test_pan_to_different_palette_with_same_luminance():
    # These different RGB565 colours have exactly the same float32 luminance.
    assert _lum565()[192] == _lum565()[2090]
    tone = dict(
        brightness=1.0, contrast=1.05, gamma=1.0, saturation=1.0, black_point=0.0, white_point=1.0
    )
    _lut_for(np.full((4, 4), 192, dtype=np.uint16), tone)
    second = np.full((4, 4), 2090, dtype=np.uint16)
    image = _rgb565_to_image(second.tobytes(), 4, 4, tone)
    assert min(image.getpixel((0, 0))) > 0
    assert image.getpixel((0, 0)) != (0, 0, 0)
