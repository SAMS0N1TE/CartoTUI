from cartotui.config import Config
from cartotui.ui.state import MapState


def _state():
    cfg = Config()
    cfg.data["traffic"]["enabled"] = False
    cfg.data["traffic"]["source"] = "disabled"
    return MapState(cfg)


def test_default_modes_per_source():
    st = _state()
    assert st.source == "vector"
    assert st.render_mode == "quadrant"
    assert st._mode_for == {"vector": "quadrant", "raster": "ascii"}


def test_toggle_source_restores_each_mode():
    st = _state()
    st.set_render_mode("braille")
    assert st._mode_for["vector"] == "braille"

    st.toggle_source()
    assert st.source == "raster"
    assert st.render_mode == "ascii"
    assert st._mode_for["vector"] == "braille"

    st.set_render_mode("half")
    assert st._mode_for["raster"] == "half"

    st.toggle_source()
    assert st.render_mode == "braille"

    st.toggle_source()
    assert st.render_mode == "half"


def test_cycle_render_mode_only_touches_current_source():
    st = _state()
    st.cycle_render_mode()
    assert st.render_mode == "braille"
    assert st._mode_for["vector"] == "braille"
    assert st._mode_for["raster"] == "ascii"


def test_set_source_is_idempotent():
    st = _state()
    st.set_source("vector")
    assert st.render_mode == "quadrant"
