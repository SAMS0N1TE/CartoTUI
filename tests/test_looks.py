from cartotui import looks
from cartotui.config import Config
from cartotui.ui.state import MapState


def _state():
    cfg = Config()
    cfg.data["traffic"]["enabled"] = False
    cfg.data["traffic"]["source"] = "disabled"
    return MapState(cfg), cfg


def test_look_registry_is_consistent():
    keys = looks.look_keys()
    assert len(keys) == len(set(keys)), "duplicate look keys"
    assert looks.default_look_key() == keys[0]
    for lk in looks.LOOKS:
        assert lk.render_mode in ("ascii", "quadrant", "braille", "half")
        assert lk.dither in ("none", "bayer", "atkinson", "floyd")
        assert lk.threshold in ("adaptive", "percentile", "edge", "fixed")
        assert 0.2 <= lk.brightness <= 3.0
        assert 0.2 <= lk.contrast <= 3.0
        assert not (lk.dither != "none" and lk.render_mode != "ascii")
        assert not (lk.render_mode == "braille" and lk.color)


def test_apply_then_detect_roundtrips_every_look():
    st, cfg = _state()
    for lk in looks.LOOKS:
        st.theme = "dark"
        looks.apply_look(st, cfg, lk)
        assert looks.current_look_key(st, cfg) == lk.key
        assert st.current_look == lk.key


def test_apply_look_persists_to_config():
    st, cfg = _state()
    lk = looks.get_look("classic")
    looks.apply_look(st, cfg, lk)
    assert cfg["render"]["color"] is False
    assert cfg["render"]["invert"] is False
    assert cfg["map"]["palette"] == lk.palette
    assert st.render_mode == "ascii"


def test_theme_bound_look_sets_theme():
    st, cfg = _state()
    changed = looks.apply_look(st, cfg, looks.get_look("paper"))
    assert st.theme == "paper"
    assert cfg["ui"]["theme"] == "paper"
    assert changed is True


def test_theme_agnostic_look_keeps_theme():
    st, cfg = _state()
    st.theme = "dark"
    changed = looks.apply_look(st, cfg, looks.get_look("classic"))
    assert st.theme == "dark"
    assert changed is False


def test_custom_settings_detect_as_none():
    st, cfg = _state()
    looks.apply_look(st, cfg, looks.get_look("terminal"))
    st.palette = "dos"
    st.dither = "floyd"
    assert looks.current_look_key(st, cfg) is None


def test_next_look_cycles_and_wraps():
    keys = looks.look_keys()
    assert looks.next_look_key(keys[0]) == keys[1]
    assert looks.next_look_key(keys[-1]) == keys[0]
    assert looks.next_look_key(None) == keys[0]
    assert looks.next_look_key("nonexistent") == keys[0]
    assert looks.next_look_key(keys[1], -1) == keys[0]


def test_guardrail_predicates():
    assert looks.dither_affects("ascii")
    assert not looks.dither_affects("quadrant")
    assert looks.shading_affects("braille")
    assert not looks.shading_affects("ascii")
    assert looks.palette_affects("ascii")
    assert not looks.palette_affects("half")


def test_affects_helpers_still_drive_the_transient_keypress_hints():
    """The persistent ⚠ notes are gone, but pressing p/d/s still says when a
    setting won't do anything in the current mode."""
    assert looks.dither_affects("ascii")
    assert not looks.dither_affects("quadrant")
    assert looks.shading_affects("quadrant")
    assert not looks.shading_affects("half")
