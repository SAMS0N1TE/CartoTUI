from types import SimpleNamespace

from cartotui.ui.map_overlay import apply_vector_overlay, clear_classify_cache


class _Tile:
    extent = 4096

    def __init__(self, layers, z, x, y):
        self.layers = layers
        self.z, self.x, self.y = z, x, y


class _Source:
    def __init__(self, layers):
        self._layers = layers

    def get_tile(self, z, x, y):
        return _Tile(self._layers, z, x, y)


def _place(name, kind, ex=2048, ey=2048, **extra):
    props = {"name": name, "kind": kind}
    props.update(extra)
    return {"geometry": {"type": "Point", "coordinates": [ex, ey]},
            "properties": props}


def _render(features, z=5):
    clear_classify_cache()
    term_w, term_h = 48, 24
    rows = [[("", " " * term_w)] for _ in range(term_h)]
    style = SimpleNamespace(label_color=(255, 220, 120))
    apply_vector_overlay(
        rows, _Source({"place_labels": {"features": features}}),
        center_lat=43.2, center_lon=-73.8, z=z,
        term_w=term_w, term_h=term_h,
        canvas_px_w=term_w * 8, canvas_px_h=term_h * 16,
        style=style,
    )
    return "".join(t for row in rows for _, t in row)


def test_country_label_is_drawn():
    text = _render([_place("Testland", "country")])
    assert "Testland" in text


def test_state_shows_even_with_high_source_min_zoom():
    text = _render([_place("Teststate", "state", min_zoom=12)], z=5)
    assert "Teststate" in text


def test_state_hidden_below_rank_min_zoom():
    text = _render([_place("Hiddenstate", "state")], z=3)
    assert "Hiddenstate" not in text


def _admin(name, level, ex=2048, ey=2048):
    return {"geometry": {"type": "Point", "coordinates": [ex, ey]},
            "properties": {"name": name, "admin_level": level}}


def _render_admin(features, z=5):
    from types import SimpleNamespace
    clear_classify_cache()
    term_w, term_h = 48, 24
    rows = [[("", " " * term_w)] for _ in range(term_h)]
    apply_vector_overlay(
        rows, _Source({"boundary_labels": {"features": features}}),
        center_lat=43.2, center_lon=-73.8, z=z,
        term_w=term_w, term_h=term_h,
        canvas_px_w=term_w * 8, canvas_px_h=term_h * 16,
        style=SimpleNamespace(label_color=(255, 220, 120)),
    )
    return "".join(t for row in rows for _, t in row)


def test_state_name_from_admin_layer():
    assert "Vermont" in _render_admin([_admin("Vermont", 4)], z=5)


def test_country_name_from_admin_layer():
    assert "Canada" in _render_admin([_admin("Canada", 2)], z=5)


def test_admin_level_above_state_ignored():
    assert "Countyville" not in _render_admin([_admin("Countyville", 6)], z=5)
