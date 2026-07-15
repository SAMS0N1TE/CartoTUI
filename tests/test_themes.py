from cartotui import theme_loader as T
from cartotui.config import Config
from cartotui.themes import apply_road_highlight, make_style, theme_vector_style

TUNED_THEMES = ("light", "paper", "green", "win31", "night")

FILL_MIN = {"water": 1.8, "park": 1.35, "building": 1.25}
ROAD_MIN = 3.0


def _rel_lum(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a, b):
    la, lb = _rel_lum(a), _rel_lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_map_chrome_bg_matches_map_bg():
    """The map Window's cell bg must be the map's own bg.

    The renderer emits fg-only styles, so flat map background is a space and
    the cell bg shows through. If that came from ui.bg, a theme whose chrome
    differs from its map (win31) would show bare chrome over the whole map.
    """
    for name in T.available_theme_names():
        t = T.resolve_theme(name)
        map_bg = (t["map"] or {}).get("bg")
        if not map_bg:
            continue
        cell_bg = T.chrome_style_map(name)["map"].split()[0]
        assert cell_bg == f"bg:{map_bg}", f"{name}: map cell bg {cell_bg} != map.bg {map_bg}"


def test_map_fills_are_visible_against_land():
    """Water/park/building must be distinguishable from the land background."""
    for name in TUNED_THEMES:
        kw = T.vector_style_kwargs(name)
        bg = kw["bg"]
        for key, floor in FILL_MIN.items():
            got = _contrast(bg, kw[key])
            assert got >= floor, f"{name}.{key} contrast {got:.2f} < {floor}"


def test_water_and_park_are_told_apart():
    for name in TUNED_THEMES:
        kw = T.vector_style_kwargs(name)
        got = _contrast(kw["water"], kw["park"])
        assert got >= 1.3, f"{name}: water vs park {got:.2f} < 1.3"


def test_roads_are_louder_than_land_fills():
    """The night hierarchy: fills sit back, roads carry the map.

    Green used to break this — its fills were as loud as night's roads, which
    made the land read as an overlay pasted over the map.
    """
    for name in TUNED_THEMES:
        kw = T.vector_style_kwargs(name)
        bg = kw["bg"]
        road = _contrast(bg, kw["road_color"])
        assert road >= ROAD_MIN, f"{name}: road contrast {road:.2f} < {ROAD_MIN}"
        for key in ("water", "park", "building"):
            fill = _contrast(bg, kw[key])
            assert fill < road, f"{name}: {key} ({fill:.2f}) not quieter than road ({road:.2f})"


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
