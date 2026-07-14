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
