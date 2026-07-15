from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

import cartotui.theme_loader as T
from cartotui.config import Config
from cartotui.ui.app import CartoTUIApp


def _app():
    cfg = Config()
    cfg.data["traffic"]["enabled"] = False
    cfg.data["traffic"]["source"] = "disabled"
    cfg.data["vector"]["source"] = "mvt_url"
    cfg.data["vector"]["mvt_url"] = ""
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        return CartoTUIApp(cfg)


def test_switching_theme_resets_image_adjust_no_leak():
    app = _app()
    try:
        app.state.brightness = 2.5
        app.state.contrast = 2.0
        app.state.dither = "floyd"
        app.state.theme = "dark"
        app._apply_theme_render("dark")
        assert abs(app.state.brightness - 1.0) < 0.01
        assert abs(app.state.contrast - 1.05) < 0.01
        assert app.state.dither == "none"
    finally:
        app.map_control.shutdown()


def test_theme_preset_restores_saved_values():
    app = _app()
    try:
        T.save_user_theme("presettest", {
            "name": "presettest",
            "ui": {"bg": "#101010", "fg": "#c0c0c0"},
            "map": {},
            "render": {"brightness": 1.6, "contrast": 1.4, "dither": "bayer"},
        })
        app.state.brightness = 1.0
        app.state.contrast = 1.05
        app._apply_theme_render("presettest")
        assert abs(app.state.brightness - 1.6) < 0.01
        assert abs(app.state.contrast - 1.4) < 0.01
        assert app.state.dither == "bayer"
    finally:
        T.delete_user_theme("presettest")
        app.map_control.shutdown()


def test_toggle_labels_flips_state_and_snapshot():
    """Map labels are place names -- separate from the aircraft labels on `a`."""
    from cartotui.config import Config
    from cartotui.ui.state import MapState

    st = MapState(Config())
    assert st.labels is True
    before = st.snapshot()
    st.toggle_labels()
    assert st.labels is False
    assert st.snapshot() != before
    st.toggle_labels()
    assert st.labels is True
