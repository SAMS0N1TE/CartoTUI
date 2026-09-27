from types import SimpleNamespace

import numpy as np
import pytest

from cartotui.themes import available_themes, theme_vector_style
from cartotui.ui.map_overlay import _extract_labels
from cartotui.ui.solid_geometry import (
    blank_frame,
    clip_segment,
    draw_solid_geometry,
    luminance,
    readable_color,
)
from cartotui.vector_source import VectorTile


def test_clipping_bounds_extreme_overzoom_work():
    assert clip_segment(-10**12, 5, 10**12, 5, 80, 24) == (0, 5, 79, 5)
    assert clip_segment(-100, -10, 100, -10, 80, 24) is None


@pytest.mark.parametrize("theme", available_themes())
def test_thin_ink_contrast_for_all_themes(theme):
    style = theme_vector_style(theme, {})
    colors = readable_color([style.water, style.road_color, style.bg], style.bg, 4.5)
    lum, bg = luminance(colors), luminance(style.bg)
    ratios = (np.maximum(lum, bg) + .05) / (np.minimum(lum, bg) + .05)
    assert np.all(ratios >= 4.45)


def test_street_and_poi_labels_use_layer_extent_and_zoom_gates():
    tile = VectorTile(z=14, x=1, y=1, extent=4096, layers={
        "street_labels": {"extent": 2048, "features": [{
            "properties": {"name": "Main Street"},
            "geometry": {"type": "LineString", "coordinates": [[200, 200], [600, 600], [1000, 1000]]}}]},
        "pois": {"features": [{"properties": {"name": "Library"},
            "geometry": {"type": "Point", "coordinates": [400, 400]}}]},
    })
    labels = {row[2]: row for row in _extract_labels(tile)}
    assert labels["Main Street"][1] == 13
    assert labels["Main Street"][3] == (1200, 1200)
    assert labels["Library"][1] == 14


def test_geometry_has_no_tile_closure_and_retains_compiled_projection():
    class Source:
        overlay_missing = 0
        calls = 0

        def get_overlay_tile(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(layers={"ocean": {"extent": 4096, "features": [{
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [4096, 0], [4096, 4096], [0, 4096], [0, 0]]]}}]}})

    source = Source()
    style = theme_vector_style("paper", {})
    kw = dict(center_lat=0, center_lon=0, z=0, term_w=80, term_h=24,
              canvas_px_w=256, canvas_px_h=256, style=style, vector_only=True)
    rows = blank_frame(80, 24, style.bg)
    assert draw_solid_geometry(rows, source, **kw) == 0
    calls = source.calls
    draw_solid_geometry(rows, source, **kw)
    assert source.calls == calls


def test_batch_clipping_matches_scalar_clipping():
    from cartotui.ui.solid_geometry import _clip_segments
    rng = np.random.default_rng(414)
    segments = rng.integers(-10000, 10000, size=(2000, 4)).astype(float)
    expected = [result for segment in segments if (result := clip_segment(*segment, 80, 24)) is not None]
    assert _clip_segments(segments, 80, 24).tolist() == [list(row) for row in expected]
