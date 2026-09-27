"""The frame must depend on the terminal and the zoom -- and nothing else."""
import pytest

from cartotui.rendering.renderer import (
    CELL_MAP_PX,
    REFERENCE_SCALE,
    Renderer,
    default_palettes,
)
from cartotui.ui.map_control import _composite_for

MODES = ("ascii", "half", "quadrant", "braille")


def _ground(cols, rows, scale, max_px=1400):
    """Tiles across, which is what decides how much map you are looking at."""
    px_w, _px_h, tile_px = _composite_for(cols, rows, scale, max_px)
    return px_w / float(tile_px)


def test_every_mode_covers_the_same_ground():
    """Switching view used to halve or double what was on screen."""
    r = Renderer(default_palettes())
    sizes = {r.cell_pixel_size(m) for m in MODES}
    assert len(sizes) == 1, "a mode still claims its own cell size: %s" % sizes


def test_the_supersample_does_not_move_the_frame():
    grounds = [_ground(176, 82, s) for s in (2, 3, 4, 6, 8)]
    assert max(grounds) - min(grounds) < 0.01, grounds


def test_the_reference_scale_frames_what_it_always_did():
    """Scale 3 must land on 256-pixel tiles, or every saved zoom shifts."""
    _w, _h, tile_px = _composite_for(176, 82, REFERENCE_SCALE, 1400)
    assert tile_px == 256


def test_a_cell_is_twice_as_tall_as_it_is_wide():
    assert CELL_MAP_PX[1] == 2 * CELL_MAP_PX[0]
    px_w, px_h, _t = _composite_for(100, 50, 3, 100000)
    assert px_w == 300 and px_h == 300


def test_the_composite_cap_costs_sharpness_not_view():
    small = _ground(400, 120, 3, max_px=1400)
    big = _ground(400, 120, 8, max_px=1400)
    assert abs(small - big) < 0.02, (small, big)
    px_w, px_h, _t = _composite_for(400, 120, 8, 1400)
    assert px_w <= 1400 and px_h <= 1400


def test_the_composite_always_has_enough_pixels_for_the_subcells():
    """Below one source pixel per subcell the native path bails to Python."""
    r = Renderer(default_palettes())
    for cols, rows in ((80, 24), (176, 82), (400, 120)):
        for scale in (2, 3, 8):
            px_w, px_h, _t = _composite_for(cols, rows, scale, 1400)
            for mode in MODES:
                sx, sy = r.subcells(mode)
                assert px_w >= cols * sx, (mode, cols, scale, px_w)
                assert px_h >= rows * sy, (mode, rows, scale, px_h)


@pytest.mark.parametrize("cols,rows", [(80, 24), (176, 82), (240, 60)])
def test_the_frame_scales_with_the_terminal(cols, rows):
    one = _ground(cols, rows, 3)
    two = _ground(cols * 2, rows, 3)
    assert abs(two - 2 * one) < 0.01


def test_tiny_view_does_not_get_stretched_to_a_64_pixel_square():
    w, h, tile = _composite_for(8, 3, 3, 1400)
    assert (w, h, tile) == (24, 18, 256)


def test_radar_keeps_geographic_extent_when_quality_changes():
    from types import SimpleNamespace

    from PIL import Image

    from cartotui.ui.map_control import MapControl
    requests = []
    def build(lat, lon, z, w, h, **kwargs):
        requests.append((w, h))
        return Image.new("RGBA", (w, h), (0, 80, 200, 100))
    control = SimpleNamespace(cfg={"overlays": {"radar": {"enabled": True}}},
                              radar_source=SimpleNamespace(build_layer=build))
    for scale in (3, 6, 8):
        w, h, tile = _composite_for(120, 40, scale, 1400)
        result = MapControl._radar_layer(control, 44, -70, 8, w, h, tile_px=tile)
        assert result.size == (w, h)
    assert requests == [(360, 240)] * 3
