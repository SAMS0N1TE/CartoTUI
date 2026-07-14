from types import SimpleNamespace

from cartotui.geodesy import latlon_to_tile_xy
from cartotui.ui.map_overlay import (
    _admin_level,
    _iter_line_coords,
    _line_cells,
    draw_boundary_lines,
)


def test_admin_level_from_number_and_class():
    assert _admin_level({"admin_level": 2}) == 2
    assert _admin_level({"admin_level": "4"}) == 4
    assert _admin_level({"class": "country"}) == 2
    assert _admin_level({"kind": "state"}) == 4
    assert _admin_level({"class": "county"}) is None
    assert _admin_level({}) is None


def test_line_cells_is_continuous():
    cells = _line_cells(0, 0, 5, 2)
    assert cells[0] == (0, 0)
    assert cells[-1] == (5, 2)
    for (ax, ay), (bx, by) in zip(cells, cells[1:]):
        assert abs(bx - ax) <= 1 and abs(by - ay) <= 1


def test_iter_line_coords_handles_multi():
    single = [[0, 0], [10, 10]]
    assert list(_iter_line_coords(single)) == [[[0, 0], [10, 10]]]
    multi = [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]
    assert len(list(_iter_line_coords(multi))) == 2


class _FakeTile:
    extent = 4096

    def __init__(self, layers):
        self.layers = layers


class _FakeSource:
    """Returns the same boundary tile for any tile coordinate in view."""

    def __init__(self, layers):
        self._layers = layers

    def get_tile(self, z, x, y):
        return _FakeTile(self._layers)


def _blank(term_w, term_h):
    return [[("", " " * term_w)] for _ in range(term_h)]


def _boundary_layers(admin_level=2, maritime=False):
    return {
        "boundaries": {
            "features": [{
                "geometry": {"type": "LineString",
                             "coordinates": [[0, 2048], [4096, 2048]]},
                "properties": {"admin_level": admin_level, "maritime": maritime},
            }]
        }
    }


def _draw(layers, z=6):
    term_w, term_h = 40, 20
    rows = _blank(term_w, term_h)
    style = SimpleNamespace(label_color=(200, 120, 255))
    n = draw_boundary_lines(
        rows, _FakeSource(layers),
        center_lat=40.0, center_lon=-100.0, z=z,
        term_w=term_w, term_h=term_h,
        canvas_px_w=term_w * 8, canvas_px_h=term_h * 16,
        style=style,
    )
    text = "".join(t for row in rows for _, t in row)
    return n, text


def test_country_boundary_is_drawn():
    n, text = _draw(_boundary_layers(admin_level=2))
    assert n > 0
    assert "═" in text


def test_maritime_boundaries_are_skipped():
    n, _ = _draw(_boundary_layers(admin_level=2, maritime=True))
    assert n == 0


def test_state_boundary_hidden_below_min_zoom():
    n_low, _ = _draw(_boundary_layers(admin_level=4), z=3)
    n_ok, _ = _draw(_boundary_layers(admin_level=4), z=6)
    assert n_low == 0
    assert n_ok > 0


def test_none_source_is_safe():
    rows = _blank(10, 5)
    assert draw_boundary_lines(
        rows, None, center_lat=0, center_lon=0, z=5,
        term_w=10, term_h=5, canvas_px_w=80, canvas_px_h=80,
        style=SimpleNamespace(label_color=(1, 2, 3))) == 0
