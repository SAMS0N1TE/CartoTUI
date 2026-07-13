from cartotui.config import DEFAULT_CONFIG, _validate


def test_defaults_roundtrip():
    c = _validate({})
    assert c["ui"]["theme"] == DEFAULT_CONFIG["ui"]["theme"]
    assert c["ui"]["panels"] == []
    assert c["render"]["vector_engine"] in ("libcarto", "python")


def test_theme_validation():
    assert _validate({"ui": {"theme": "dark"}})["ui"]["theme"] == "dark"
    assert _validate({"ui": {"theme": "Night"}})["ui"]["theme"] == "night"
    assert _validate({"ui": {"theme": "nope"}})["ui"]["theme"] == DEFAULT_CONFIG["ui"]["theme"]


def test_numeric_clamping():
    c = _validate({
        "viewport": {"sidebar_width": 999},
        "overlays": {"radar": {"opacity": 5, "color": 99, "frame_interval": 0.01}},
        "snapshot": {"png_long_side": 99999},
    })
    assert c["viewport"]["sidebar_width"] == 120
    assert c["overlays"]["radar"]["opacity"] == 1.0
    assert c["overlays"]["radar"]["color"] == 8
    assert c["overlays"]["radar"]["frame_interval"] == 0.15
    assert c["snapshot"]["png_long_side"] == 6144


def test_choices():
    assert _validate({"traffic": {"source": "weird"}})["traffic"]["source"] == "disabled"
    assert _validate({"render": {"vector_render_mode": "half"}})["render"]["vector_render_mode"] == "half"
    assert _validate({"map": {"mode": "half"}})["map"]["mode"] == "half"


def test_dynamic_quality_defaults():
    c = _validate({})
    assert c["render"]["dynamic_quality"] is True
    assert _validate({"render": {"dynamic_quality": False}})["render"]["dynamic_quality"] is False


def test_perf_settings():
    c = _validate({})
    assert c["ui"]["max_fps"] == 30
    assert c["render"]["color_depth"] == "truecolor"
    assert _validate({"ui": {"max_fps": 999}})["ui"]["max_fps"] == 120
    assert _validate({"render": {"color_depth": "bad"}})["render"]["color_depth"] == "truecolor"
    assert _validate({"render": {"color_depth": "256"}})["render"]["color_depth"] == "256"


def test_unknown_nested_keys_preserved():
    c = _validate({"traffic": {"lakeshark": {"tx_pin": 48, "baudrate": 921600}}})
    assert c["traffic"]["lakeshark"]["tx_pin"] == 48
    assert c["traffic"]["lakeshark"]["baudrate"] == 921600


def test_panels_list_normalised():
    assert _validate({"ui": {"panels": "bad"}})["ui"]["panels"] == []
    assert _validate({"ui": {"panels": [{"name": "compass"}]}})["ui"]["panels"] == [{"name": "compass"}]
