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
