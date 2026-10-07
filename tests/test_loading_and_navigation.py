from types import SimpleNamespace

from PIL import Image
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from test_settings import make_app

from cartotui.config import Config
from cartotui.radar import RadarSource
from cartotui.ui.state import MapState
from cartotui.ui.statusbar import StatusBar


def test_radar_progress_distinguishes_metadata_tiles_and_retries(monkeypatch):
    rs = RadarSource()
    assert "waiting for frames" in rs.progress_text()
    def get(*args, **kwargs):
        assert "getting frames" in rs.progress_text()
        raise OSError("offline")
    monkeypatch.setattr("requests.get", get)
    rs.refresh_frames(force=True)
    assert "failed" in rs.progress_text()
    assert not rs._meta_loading
    rs._meta_error = False
    rs._past = [{"time": 1, "path": "/frame"}]
    rs._visible_keys = {"a", "b", "c", "d"}
    rs._cache["a"] = Image.new("RGBA", (1, 1))
    rs._cache["b"] = Image.new("RGBA", (1, 1))
    assert "[####....] 2/4 tiles" in rs.progress_text()
    rs._retry_after["c"] = 99
    assert "2/4 retrying" in rs.progress_text()
    for key in rs._visible_keys:
        rs._cache[key] = Image.new("RGBA", (1, 1))
    assert "[########] 4/4 ready" in rs.progress_text()
    # A pan must count the new visible set, not all previously downloaded tiles.
    rs._visible_keys = {"a", "e"}
    assert "1/2 tiles" in rs.progress_text()
    rs.close()


def test_radar_progress_visible_on_phone_width():
    cfg = Config()
    cfg.data["overlays"]["radar"]["enabled"] = True
    bar = StatusBar(MapState(cfg), cfg)
    bar.radar_source = SimpleNamespace(progress_text=lambda: "Radar [####....] 2/4 tiles")
    text = "".join(t for _, t in bar.create_content(32, 1).get_line(0))
    assert text.startswith("Radar [####....] 2/4 tiles")
    assert len(text) == 32


def test_back_and_close_have_visible_click_targets_and_sizing_is_cached():
    app = make_app()
    try:
        menu = app.sidebar.control
        menu.open_page("render")
        content = menu.create_content(32, 22)
        assert "[ Back ]" in "".join(t for _, t in content.get_line(1))
        menu.mouse_handler(MouseEvent(Point(5, 1), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
        assert menu.page == "home"
        menu.create_content(32, 22)
        menu.mouse_handler(MouseEvent(Point(15, 1), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
        assert not app.state.sidebar_visible
        menu._body = lambda width: (_ for _ in ()).throw(AssertionError("layout rebuilt widgets"))
        assert menu.compact_height() > 0
    finally:
        app.map_control.shutdown()
        app.radar_source.close()


def test_phone_toolbar_exposes_both_zoom_directions():
    app = make_app()
    try:
        calls = []
        app.map_control.zoom = calls.append
        text = "".join(t for _, t in app.toolbar.create_content(36, 1).get_line(0))
        assert "Menu" in text and "View" in text
        assert "+" in text and "-" in text
        app.toolbar._dispatch("-")
        app.toolbar._dispatch("+")
        assert calls == [-1, 1]
    finally:
        app.map_control.shutdown()
        app.radar_source.close()
