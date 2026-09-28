import re
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from prompt_toolkit.output import ColorDepth

from cartotui.rendering.packed import PackedFrame, encoder
from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.ui.aircraft_overlay import _stamp_cells_batch, _stamp_label
from cartotui.ui.direct_paint import paint_rows

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/experiments"))
from performance_research import emulate  # noqa: E402


def screen(text, w, h, initial=None):
    def rgb(m):
        v = (int(m[2]) << 16) | (int(m[3]) << 8) | int(m[4])
        return f"\x1b[{m[1]};5;{v}m"

    text = re.sub(r"\x1b\[(38|48);2;(\d+);(\d+);(\d+)m", rgb, text)
    text = text.replace("\x1b[39m", "\x1b[38;5;16777216m")
    text = text.replace("\x1b[49m", "\x1b[48;5;16777216m")
    return emulate(text.encode(), w, h, initial)


@pytest.mark.parametrize("depth", [8, 24])
@pytest.mark.parametrize("mode", ["half", "braille", "quadrant", "ascii"])
@pytest.mark.parametrize("radar", [False, True])
def test_packed_frame_matches_fragment_pixels(depth, mode, radar):
    enc = encoder()
    if enc is None:
        pytest.skip("new native terminal library unavailable")
    rng = np.random.default_rng(13)
    image = Image.fromarray(rng.integers(0, 256, (96, 96, 3), dtype=np.uint8))
    overlay = Image.new("RGBA", image.size, (40, 180, 80, 120)) if radar else None
    r = Renderer(default_palettes(), subpixel_threshold="stable")
    kw = dict(mode=mode, overlay=overlay)
    rows = r.render(image, 32, 16, True, **kw)
    packed = r.render(image, 32, 16, True, packed=True, **kw)
    if not isinstance(packed, PackedFrame):
        # Python-only quadrant/ascii overlay paths remain supported fallbacks.
        assert packed == rows
        return
    for frame in (rows, packed):
        _stamp_cells_batch(frame, 32, [(2, 4, "•", "fg:#ff1234"), (2, 4, "+", "fg:#ffff00")])
        _stamp_label(frame, 32, -2, 7, "Border town", "fg:#ffaacc bg:#123456")
    cd = ColorDepth.DEPTH_8_BIT if depth == 8 else ColorDepth.DEPTH_24_BIT
    blocked = [(7, 2, 13, 8)]
    expected = paint_rows(rows, 0, 0, 32, 16, blocked, "abcdef", "020408", cd)
    actual, prev = enc.paint(packed, 0, 0, blocked, "abcdef", "020408", depth)
    assert screen(actual, 32, 16) == screen(expected, 32, 16)
    assert enc.paint(packed, 0, 0, blocked, "abcdef", "020408", depth, prev)[0] == ""
    changed = packed.copy()
    changed.stamp(1, 1, "X", "fg:#ffff00 bg:#030609")
    delta, _ = enc.paint(changed, 0, 0, blocked, "abcdef", "020408", depth, prev)
    full, _ = enc.paint(changed, 0, 0, blocked, "abcdef", "020408", depth)
    assert screen(delta, 32, 16, screen(actual, 32, 16)) == screen(full, 32, 16)
    exposed, _ = enc.paint(changed, 0, 0, [], "abcdef", "020408", depth)
    assert all(c is not None for c in screen(exposed, 32, 16))


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("threshold", ["stable", "adaptive", "fixed", "percentile"])
def test_unshaded_braille_preserves_palette_tones(native, threshold):
    r = Renderer(default_palettes(), use_native_cells=native, subpixel_threshold=threshold)
    a = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 3, axis=2)
    image = Image.fromarray(np.repeat(a, 32, axis=0))
    for radar in (None, Image.new("RGBA", image.size, (0, 200, 255, 100))):
        rows = r.render(image, 128, 8, True, mode="braille", overlay=radar)
        chars = "".join(text for row in rows for _, text in row)
        palette = set(default_palettes()["dos5"])
        assert all(ch in palette or 0x2800 <= ord(ch) <= 0x28FF for ch in chars)
        assert set(chars) & (palette - {" "})
        assert all("bg:" not in style for row in rows for style, _ in row)
        assert len({style for row in rows for style, _ in row}) > 2


def test_native_rgb_expansion_is_byte_exact():
    from cartotui.rendering.libcarto_backend import _image_from
    rng = np.random.default_rng(231)
    indices = rng.integers(0, 65536, (47, 83), dtype=np.uint16)
    lut = rng.integers(0, 2**32, 65536, dtype=np.uint32)
    expected = Image.frombuffer("RGBA", (83,47), lut[indices], "raw", "RGBA", 0, 1).convert("RGB")
    assert _image_from(indices,83,47,lut).tobytes() == expected.tobytes()


def test_native_pixel_kernels_match_numpy_rounding(monkeypatch):
    import cartotui.rendering.renderer as module
    rng = np.random.default_rng(909)
    base = rng.integers(0, 256, (257, 513, 3), dtype=np.uint8)
    overlay = rng.integers(0, 256, base.shape, dtype=np.uint8)
    alpha = rng.integers(0, 256, base.shape[:2], dtype=np.uint8).astype(np.float32) / 255
    native_lum = module._luminance(base)
    native_blend = module._Overlay(overlay, alpha, None).over(base)
    monkeypatch.setattr(module, "_native_renderer", lambda: None)
    np.testing.assert_array_equal(native_lum, module._luminance(base))
    np.testing.assert_array_equal(native_blend, module._Overlay(overlay, alpha, None).over(base))
