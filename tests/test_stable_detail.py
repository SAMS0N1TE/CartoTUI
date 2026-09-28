import numpy as np
import pytest
from PIL import Image

from cartotui.rendering.renderer import Renderer, _native_renderer, default_palettes
from cartotui.rendering.threshold import compute_fill_levels


def test_distant_content_cannot_change_local_features():
    a = np.full((96, 160), 0.08, np.float32)
    a[20:70, 30:32] = 0.35
    b = a.copy()
    b[:, 85:] = 0.95
    args = dict(levels=256, threshold_mode="stable", orientation="dark")
    np.testing.assert_array_equal(
        compute_fill_levels(a, **args)[:, :80], compute_fill_levels(b, **args)[:, :80]
    )


@pytest.mark.parametrize("width", [1, 2, 4, 8, 16, 32])
def test_thin_and_wide_roads_survive(width):
    a = np.full((80, 96), 0.08, np.float32)
    a[:, 32 : 32 + width] = 0.35
    result = compute_fill_levels(a, 256, "stable", orientation="dark")
    assert (result[:, 32 : 32 + width] >= 80).all()
    assert (result[:, :28] < 80).all()


def test_small_noise_does_not_become_full_ink():
    rng = np.random.default_rng(9)
    a = (0.08 + rng.uniform(-0.005, 0.005, (64, 64))).astype(np.float32)
    assert compute_fill_levels(a, 256, "stable", orientation="dark").max() < 80


@pytest.mark.parametrize("shape", [(1, 1), (1, 17), (19, 1)])
def test_tiny_viewports(shape):
    result = compute_fill_levels(np.full(shape, 0.2, np.float32), 5, "stable")
    assert result.shape == shape


@pytest.mark.parametrize("mode", ["ascii", "quadrant", "braille", "half"])
@pytest.mark.parametrize("orientation", ["dark", "bright"])
def test_native_and_python_agree(mode, orientation):
    native = _native_renderer()
    if native is None or not getattr(native, "has_stable_cells", False):
        pytest.skip("updated native library not built")
    a = np.random.default_rng(4).integers(0, 256, (96, 120, 3), dtype=np.uint8)
    img = Image.fromarray(a)
    r = Renderer(default_palettes(), subpixel_threshold="stable")
    actual = r.render(img, 30, 24, True, mode, orientation=orientation)
    r.use_native_cells = False
    expected = r.render(img, 30, 24, True, mode, orientation=orientation)

    def cells(rows):
        return [[(s, c) for s, text in row for c in text] for row in rows]

    assert cells(actual) == cells(expected)


def test_half_is_independent_of_threshold():
    img = Image.new("RGB", (20, 20), (32, 56, 106))
    r = Renderer(default_palettes())
    baseline = r.render(img, 10, 10, True, "half")
    for mode in ("stable", "fixed", "edge", "percentile"):
        r.update_options(subpixel_threshold=mode)
        assert r.render(img, 10, 10, True, "half") == baseline


@pytest.mark.parametrize("orientation", ["dark", "bright"])
def test_broad_fill_leaves_contrast_for_roads(orientation):
    # Typical dark-map tones: water/park versus minor/major roads.
    values = np.array([[0.30, 0.40, 0.58, 0.80]], dtype=np.float32)
    signal = np.repeat(np.repeat(values, 16, axis=0), 16, axis=1)
    lum = signal if orientation == "dark" else 1.0 - signal
    fill = compute_fill_levels(lum, 256, "stable", orientation=orientation)[8, 8::16]
    assert fill[1] < 110
    assert int(fill[3]) - int(fill[0]) > 150
    assert np.all(np.diff(fill.astype(int)) > 30)


def test_pan_preserves_weather_and_map_in_shared_area():
    # A distant rain cell entering view must not change an existing weather band.
    base = np.full((40, 100), .30, np.float32)
    rain = np.full_like(base, .35)
    alpha = np.full_like(base, .65)
    changed = rain.copy()
    changed[:, 60:] = .95
    args = dict(levels=256, threshold_mode="stable", orientation="dark", overlay_alpha=alpha)
    np.testing.assert_array_equal(
        compute_fill_levels(base, overlay_lum=rain, **args)[:, :50],
        compute_fill_levels(base, overlay_lum=changed, **args)[:, :50],
    )


@pytest.mark.parametrize("mode", ["ascii", "braille"])
def test_panning_shared_cells_matches_fresh_frame(mode):
    # Shift by whole cells; exclude the local filter's two-sample edge radius.
    rng = np.random.default_rng(81)
    pixels = rng.integers(0, 256, (96, 160, 3), dtype=np.uint8)
    r = Renderer(default_palettes(), subpixel_threshold="stable")
    sx, sy = r.subcells(mode)
    first = r.render(Image.fromarray(pixels[:, :120]), 120 // sx, 96 // sy,
                     True, mode, palette_name="dos5", orientation="dark", packed=True)
    second = r.render(Image.fromarray(pixels[:, 8:128]), 120 // sx, 96 // sy,
                      True, mode, palette_name="dos5", orientation="dark", packed=True)
    np.testing.assert_array_equal(first.glyph[:, 8 // sx + 3:-3], second.glyph[:, 3:-8 // sx - 3])


def test_stable_tone_is_independent_of_distant_colours():
    from cartotui.composite import apply_image_adjustments
    from cartotui.rendering.libcarto_backend import _rgb565_to_image
    tone = dict(brightness=1.0, contrast=1.4, gamma=1.0, saturation=1.0,
                black_point=0.0, white_point=1.0, contrast_pivot=0.5)
    first = np.full((16, 64), 0x4A69, np.uint16)
    second = first.copy()
    second[:, 32:] = 0xFFFF
    native_a = np.asarray(_rgb565_to_image(first.tobytes(), 64, 16, tone))
    native_b = np.asarray(_rgb565_to_image(second.tobytes(), 64, 16, tone))
    np.testing.assert_array_equal(native_a[:, :32], native_b[:, :32])
    for indices, expected in ((first, native_a), (second, native_b)):
        raw = _rgb565_to_image(indices.tobytes(), 64, 16)
        np.testing.assert_array_equal(np.asarray(apply_image_adjustments(raw, **tone)), expected)
