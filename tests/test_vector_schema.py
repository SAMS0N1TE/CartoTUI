
from __future__ import annotations

from cartotui.raster_vector import ROAD_CLASS_PRIORITY, rasterise_view
from cartotui.themes import theme_vector_style

class _FakeTile:
    extent = 4096

    def __init__(self, layers):
        self.layers = layers

class _FakeSource:

    def __init__(self, layers):
        self._tile = _FakeTile(layers)

    def get_tile(self, z, x, y):
        return self._tile

def _road_layer(name):
    return {name: {"features": [
        {"geometry": {"type": "LineString",
                      "coordinates": [[0, 0], [4096, 4096]]},
         "properties": {"kind": "motorway"}},
        {"geometry": {"type": "LineString",
                      "coordinates": [[0, 4096], [4096, 0]]},
         "properties": {"kind": "motorway"}},
    ]}}

def _water_layer(name):
    return {name: {"features": [{
        "geometry": {"type": "Polygon",
                     "coordinates": [[[0, 0], [4096, 0], [4096, 4096],
                                      [0, 4096], [0, 0]]]},
        "properties": {},
    }]}}

def _colors(img):
    cols = img.getcolors(maxcolors=100000) or []
    return {c for _, c in cols}

def _render(layers):
    style = theme_vector_style("dark", {})
    src = _FakeSource(layers)
    img = rasterise_view(src, 0.0, 0.0, 13, 200, 200, style=style)
    return img, style

def _motorway_color(style):
    return style.color_for_priority(ROAD_CLASS_PRIORITY["motorway"])

def test_shortbread_streets_render():
    img, style = _render(_road_layer("streets"))
    assert _motorway_color(style) in _colors(img)

def test_protomaps_roads_render():
    img, style = _render(_road_layer("roads"))
    assert _motorway_color(style) in _colors(img)

def test_unknown_road_layer_draws_nothing():
    img, style = _render(_road_layer("totally_unknown_layer"))
    assert _motorway_color(style) not in _colors(img)

def test_shortbread_water_polygons_render():
    img, style = _render(_water_layer("water_polygons"))
    assert style.water in _colors(img)

def test_protomaps_water_render():
    img, style = _render(_water_layer("water"))
    assert style.water in _colors(img)
