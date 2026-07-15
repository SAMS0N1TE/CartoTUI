"""Tone controls: they must move tone without blowing out or draining colour."""
import numpy as np
from PIL import Image

from cartotui.composite import apply_image_adjustments


def _scene(bg=(20, 24, 40)):
    """A flat field with a few saturated features -- enough to measure chroma."""
    a = np.zeros((60, 90, 3), dtype=np.uint8)
    a[:, :] = bg
    a[10:20, 10:40] = (200, 40, 30)
    a[25:35, 10:40] = (30, 160, 60)
    a[40:50, 10:40] = (40, 70, 200)
    a[10:50, 55:85] = (128, 128, 128)
    return Image.fromarray(a, "RGB")


def _lum_arr(img):
    a = np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def _lum(img):
    return float(_lum_arr(img).mean())


def _sat(img):
    a = np.asarray(img.convert("RGB"), dtype=np.float64)
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    return float(np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0).mean())


def test_neutral_params_are_a_noop():
    img = _scene()
    out = apply_image_adjustments(img)
    assert np.array_equal(np.asarray(img), np.asarray(out))


def test_contrast_below_one_does_not_desaturate():
    """The old enhancer blended toward flat grey, so lowering contrast drained
    colour instead of flattening tone."""
    img = _scene()
    for c in (0.4, 0.7):
        out = apply_image_adjustments(img, contrast=c)
        assert abs(_sat(out) - _sat(img)) < 0.02, f"contrast {c} shifted saturation"


def test_contrast_above_one_does_not_blow_out():
    img = _scene(bg=(120, 125, 130))
    out = apply_image_adjustments(img, contrast=2.5)
    a = np.asarray(out)
    assert (a >= 255).all(axis=-1).mean() < 0.02


def test_brightness_keeps_hue():
    """A multiply clips channels independently and shifts hue; the shoulder
    plus gamut mapping has to keep red reading as red."""
    img = Image.new("RGB", (8, 8), (200, 40, 30))
    r, g, b = np.asarray(apply_image_adjustments(img, brightness=2.5))[0, 0].tolist()
    assert r > g and r > b


def test_brightness_is_monotonic_and_bounded():
    img = _scene()
    last = _lum(img)
    for f in (1.2, 1.6, 2.0, 3.0):
        cur = _lum(apply_image_adjustments(img, brightness=f))
        assert cur >= last - 1e-6, "brightness must not go backwards"
        assert cur <= 1.0
        last = cur


def test_black_point_lifts_pure_black():
    """Themes with a #000000 background are the reason this control exists: a
    ratio-based re-tint alone cannot move a black pixel."""
    img = Image.new("RGB", (8, 8), (0, 0, 0))
    out = np.asarray(apply_image_adjustments(img, black_point=0.25))[0, 0]
    assert out.min() > 40, f"black point did not lift pure black: {out}"


def test_black_point_raises_floor_without_clipping():
    img = _scene()
    base = _lum(img)
    out = apply_image_adjustments(img, black_point=0.25)
    assert _lum(out) > base
    assert abs(_sat(out) - _sat(img)) < 0.03
    assert (np.asarray(out) >= 255).all(axis=-1).mean() < 0.02


def test_white_point_lowers_ceiling():
    img = _scene(bg=(220, 220, 210))
    base = _lum(img)
    out = apply_image_adjustments(img, white_point=0.6)
    assert _lum(out) < base, "white point must tame a bright theme"
    assert _lum_arr(out).max() <= 0.6 + 0.02
    assert abs(_sat(out) - _sat(img)) < 0.03


def test_levels_bound_luminance():
    """Levels cap luminance, not channels: a saturated blue sits at luma 0.11,
    so lifting it to a high floor legitimately pins its blue channel at full
    while the pixel's luminance still lands inside the window."""
    img = _scene()
    for bp, wp in ((0.0, 1.0), (0.2, 0.8), (0.4, 0.6), (0.05, 0.95)):
        out = apply_image_adjustments(img, black_point=bp, white_point=wp)
        lum = _lum_arr(out)
        assert lum.min() >= bp - 0.02
        assert lum.max() <= wp + 0.02
        assert (np.asarray(out) >= 255).all(axis=-1).mean() < 0.02


def test_crossed_levels_do_not_invert():
    """A floor above the ceiling would flip the map; the pair gets ordered."""
    img = _scene()
    lum = _lum_arr(apply_image_adjustments(img, black_point=0.8, white_point=0.2))
    assert lum.min() >= 0.2 - 0.02
    assert lum.max() <= 0.8 + 0.02


def test_saturation_scales_chroma_without_moving_tone():
    img = _scene()
    base_l, base_s = _lum(img), _sat(img)
    grey = apply_image_adjustments(img, saturation=0.0)
    assert _sat(grey) < 0.01
    assert abs(_lum(grey) - base_l) < 0.02, "desaturating must not shift luminance"
    vivid = apply_image_adjustments(img, saturation=1.8)
    assert _sat(vivid) > base_s
    assert abs(_lum(vivid) - base_l) < 0.02


def test_gamma_moves_midtones():
    img = _scene(bg=(128, 128, 128))
    up = _lum(apply_image_adjustments(img, gamma=2.0))
    down = _lum(apply_image_adjustments(img, gamma=0.5))
    assert up > _lum(img) > down
