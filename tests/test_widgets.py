import pytest

from cartotui.config import Config
from cartotui.snapshot import frame_to_html
from cartotui.ui.state import MapState
from cartotui.ui.widgets import (
    DEFAULT_WIDGET_ORDER,
    WidgetContext,
    WidgetManager,
    widget_names,
)


def _manager():
    cfg = Config()
    state = MapState(cfg)
    ctx = WidgetContext(state=state, cfg=cfg)
    return WidgetManager(ctx, order=DEFAULT_WIDGET_ORDER)


def test_registry_has_widgets():
    for name in DEFAULT_WIDGET_ORDER:
        assert name in widget_names()


def test_all_panels_render():
    mgr = _manager()
    assert mgr.all_names() == DEFAULT_WIDGET_ORDER
    for name in mgr.all_names():
        panel = mgr.panel(name)
        h = panel.height()
        content = panel.create_content(panel.width, h)
        lines = [content.get_line(i) for i in range(h)]
        assert len(lines) == h


def test_collapse_and_show_hide():
    mgr = _manager()
    p = mgr.panel("compass")
    assert not p.collapsed
    p._toggle_collapse()
    assert p.collapsed and p.height() == 1
    p._toggle_collapse()
    mgr.show("compass")
    assert mgr.is_visible("compass")
    mgr.hide("compass")
    assert not mgr.is_visible("compass")


def test_drag_moves_including_up():
    mgr = _manager()
    mgr.set_screen(120, 40)
    p = mgr.panel("compass")
    mgr._ensure_float(p)
    fobj = p.float
    mgr.begin_drag(p, 3, 0)
    mgr.drag_to(50, 5)
    assert (p.top, p.left) == (5, 47)
    mgr.drag_to(50, 1)
    assert p.top == 1
    assert p.float is fobj
    mgr.end_drag()
    assert not mgr.is_dragging()


def test_frame_to_html_resolves_colors():
    rows = [[("fg:#ff0000", "hi"), ("class:map", " x")], [("bg:#0000ff fg:#ffffff", "y")]]
    html = frame_to_html(rows, "night", "t")
    assert "color:#ff0000" in html
    assert "background:#0000ff" in html
    assert "<pre>" in html


def _tone_widget(name):
    cfg = Config()
    state = MapState(cfg)
    ctx = WidgetContext(state=state, cfg=cfg)
    from cartotui.ui.widgets.registry import create_widget
    w = create_widget(name, ctx)
    return w, state


def _rows_and_hits(w, width):
    return w.render_body(width)


def _click(w, width, y, x):
    """Fire the hit under (y, x), as the panel's mouse handler would."""
    _lines, hits = _rows_and_hits(w, width)
    for (hy, x0, x1, fn) in hits:
        if hy == y and x0 <= x < x1:
            fn()
            return True
    return False


def _find_row(w, width, label):
    lines, _ = _rows_and_hits(w, width)
    for y, line in enumerate(lines):
        if any(label in text for _s, text in line):
            return y, line
    raise AssertionError(f"row {label!r} not found")


@pytest.mark.parametrize("name", ["render", "theme"])
def test_tone_fold_toggles_and_reveals_knobs(name):
    w, _state = _tone_widget(name)
    width = w.default_width - 2

    assert w._tone_open is False
    folded = len(_rows_and_hits(w, width)[0])
    y, _ = _find_row(w, width, "Tone")
    assert _click(w, width, y, 1), "fold header is not clickable"
    assert w._tone_open is True

    opened = len(_rows_and_hits(w, width)[0])
    assert opened > folded
    for label in ("Brightness", "Contrast", "Gamma", "Saturation",
                  "Black pt", "White pt", "Reset tone"):
        _find_row(w, width, label)


@pytest.mark.parametrize("name", ["render", "theme"])
def test_tone_minus_and_plus_hits_move_the_right_knob(name):
    w, state = _tone_widget(name)
    width = w.default_width - 2
    w._tone_open = True

    for label, attr, step, seed in (("Brightness", "brightness", 0.1, 1.0),
                                    ("Contrast", "contrast", 0.1, 1.05),
                                    ("Gamma", "gamma", 0.1, 1.0),
                                    ("Saturation", "saturation", 0.1, 1.0),
                                    ("Black pt", "black_point", 0.02, 0.10),
                                    ("White pt", "white_point", 0.02, 0.90)):
        setattr(state, attr, seed)
        y, _line = _find_row(w, width, label)
        assert _click(w, width, y, width - 2), f"{label} [+] not clickable"
        assert getattr(state, attr) == pytest.approx(seed + step, abs=1e-6), label
        assert _click(w, width, y, _minus_x(w, width, y)), f"{label} [-] not clickable"
        assert getattr(state, attr) == pytest.approx(seed, abs=1e-6), label


def test_levels_clicks_stop_at_their_limits():
    """Black point rests on its floor, white point on its ceiling."""
    w, state = _tone_widget("render")
    width = w.default_width - 2
    w._tone_open = True

    y, _ = _find_row(w, width, "White pt")
    assert _click(w, width, y, width - 2)
    assert state.white_point == 1.0

    y, _ = _find_row(w, width, "Black pt")
    assert _click(w, width, y, _minus_x(w, width, y))
    assert state.black_point == 0.0


def _minus_x(w, width, y):
    _lines, hits = _rows_and_hits(w, width)
    xs = sorted(x0 for (hy, x0, _x1, _fn) in hits if hy == y)
    return xs[0]


def test_reset_tone_button_restores_defaults():
    w, state = _tone_widget("render")
    width = w.default_width - 2
    w._tone_open = True
    state.adjust_black_point(+0.1)
    state.adjust_saturation(+0.5)
    y, _ = _find_row(w, width, "Reset tone")
    assert _click(w, width, y, 2)
    assert state.black_point == 0.0
    assert state.saturation == 1.0


def test_render_widget_labels_toggle():
    w, state = _tone_widget("render")
    width = w.default_width - 2
    y, _ = _find_row(w, width, "Labels")
    assert state.labels is True
    assert _click(w, width, y, 1)
    assert state.labels is False


def _adsb_widget(source="api"):
    from cartotui.traffic.adsb_api import ADSBApiSource
    from cartotui.traffic.aircraft import AircraftRegistry
    from cartotui.ui.widgets.registry import create_widget

    cfg = Config()
    cfg.data["traffic"]["source"] = source
    state = MapState(cfg)
    reg = AircraftRegistry()
    src = ADSBApiSource(reg) if source == "api" else None
    ctx = WidgetContext(state=state, cfg=cfg, aircraft_registry=reg,
                        get_traffic=(lambda: src))
    return create_widget("adsb", ctx), cfg, src


def test_adsb_update_and_radius_rows_adjust_live_and_persist():
    """The poll loop re-reads interval_s each cycle, so the widget must push the
    value at the running source, not just write config."""
    w, cfg, src = _adsb_widget()
    width = w.default_width - 2

    y, _ = _find_row(w, width, "Update")
    assert _click(w, width, y, _minus_x(w, width, y))
    assert cfg.data["traffic"]["api"]["interval_s"] == pytest.approx(4.5)
    assert src.interval_s == pytest.approx(4.5)

    y, _ = _find_row(w, width, "Radius")
    assert _click(w, width, y, width - 2)
    assert cfg.data["traffic"]["api"]["radius_nm"] == pytest.approx(125)
    assert src.radius_nm == 125


def test_adsb_update_row_bottoms_out_at_half_a_second():
    w, cfg, _src = _adsb_widget()
    width = w.default_width - 2
    for _ in range(40):
        y, _ = _find_row(w, width, "Update")
        _click(w, width, y, _minus_x(w, width, y))
    assert cfg.data["traffic"]["api"]["interval_s"] == pytest.approx(0.5)


def test_adsb_update_row_tops_out_at_ten_seconds():
    w, cfg, _src = _adsb_widget()
    width = w.default_width - 2
    for _ in range(40):
        y, _ = _find_row(w, width, "Update")
        _click(w, width, y, width - 2)
    assert cfg.data["traffic"]["api"]["interval_s"] == pytest.approx(10.0)


def test_adsb_shows_streaming_for_a_source_without_a_poll_interval():
    """A receiver pushes messages as they arrive; a poll knob would be a lie."""
    from cartotui.traffic.sbs1 import SBS1TCPSource
    from cartotui.traffic.aircraft import AircraftRegistry
    from cartotui.ui.widgets.registry import create_widget

    cfg = Config()
    reg = AircraftRegistry()
    src = SBS1TCPSource(reg)
    ctx = WidgetContext(state=MapState(cfg), cfg=cfg, aircraft_registry=reg,
                        get_traffic=(lambda: src))
    w = create_widget("adsb", ctx)
    width = w.default_width - 2
    _y, line = _find_row(w, width, "Update")
    assert "streaming" in "".join(t for _s, t in line)


def test_adsb_settings_fold_keeps_the_panel_off_the_row_cap():
    """With a link and a selection this panel already runs to the 40-row body
    cap, past which rows are dropped rather than scrolled."""
    w, _cfg, _src = _adsb_widget()
    width = w.default_width - 2

    assert w._display_open is False
    y, _ = _find_row(w, width, "Display")
    assert _click(w, width, y, 1)
    assert w._display_open is True
    for label in ("Labels", "Markers", "Size", "Trails"):
        _find_row(w, width, label)


def test_adsb_marker_size_cycles():
    w, cfg, _src = _adsb_widget()
    width = w.default_width - 2
    w._display_open = True
    y, _ = _find_row(w, width, "Size")
    assert _click(w, width, y, 1)
    assert cfg.data["aircraft"]["marker_size"] == "large"


def test_adsb_trail_length_adjusts():
    w, cfg, _src = _adsb_widget()
    width = w.default_width - 2
    w._display_open = True
    y, _ = _find_row(w, width, "length")
    assert _click(w, width, y, width - 2)
    assert cfg.data["aircraft_trails"]["duration_s"] == pytest.approx(75.0)
