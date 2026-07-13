from cartotui import theme_loader as T
from cartotui.config import Config
from cartotui.themes import apply_road_highlight, make_style, theme_vector_style


def test_all_builtins_present():
    names = T.available_theme_names()
    assert len(names) == 10
    for n in ("amber", "dark", "night", "paper", "win31"):
        assert n in names


def test_chrome_map_complete():
    for name in T.available_theme_names():
        cm = T.chrome_style_map(name)
        for cls in ("sidebar", "map", "panel.title", "titlebar.hotkey"):
            assert cls in cm and cm[cls]


def test_vector_style_has_full_road_ramp():
    for name in T.available_theme_names():
        vs = theme_vector_style(name)
        assert len(vs.road_colors) == 10
        for p in range(1, 11):
            assert len(vs.road_colors[p]) == 3


def test_user_overrides():
    vs = theme_vector_style("amber", {"label": "#00ff00", "road_colors": {"motorway": [1, 2, 3]}})
    assert vs.label_color == (0, 255, 0)
    assert vs.road_colors[10] == (1, 2, 3)


def test_road_highlight_thickens_and_brightens():
    base = theme_vector_style("dark")
    hi = apply_road_highlight(theme_vector_style("dark"))
    assert hi.road_widths[10] > base.road_widths[10]
    assert sum(hi.road_color) >= sum(base.road_color)


def test_make_style_builds():
    cfg = Config()
    cfg.data["ui"]["theme"] = "green"
    assert make_style(cfg) is not None


def test_hex_helpers():
    assert T._hex_to_rgb("#ff8000") == (255, 128, 0)
    assert T._hex_to_rgb("f80") == (255, 136, 0)
    assert T._blend("#000000", "#ffffff", 0.5) == "#808080"
