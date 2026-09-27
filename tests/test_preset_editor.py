import pytest

from cartotui import theme_loader as T
from cartotui.config import Config
from cartotui.presets import apply_settings, capture_settings, preset_name
from cartotui.themes import theme_vector_style
from cartotui.ui.state import MapState
from cartotui.ui.widgets.base import WidgetContext
from cartotui.ui.widgets.theme_widget import ThemeWidget, parse_color


@pytest.mark.parametrize('value', ['../bad', 'a/b', 'C:\\oops', '', 'nul', 'CON'])
def test_invalid_names_cannot_escape_preset_directory(value):
    with pytest.raises(ValueError):
        preset_name(value)


def test_color_entry():
    assert parse_color('Cyan') == '#77d8df'
    assert parse_color('#f80') == '#ff8800'
    with pytest.raises(ValueError):
        parse_color('bg:red')


def test_live_label_edit_and_undo_do_not_write_or_reapply_preset(monkeypatch):
    cfg = Config()
    state = MapState(cfg)
    state.contrast = 1.7
    monkeypatch.setattr(T, 'save_user_theme', lambda *a: pytest.fail('unexpected save'))
    w = ThemeWidget(WidgetContext(state=state, cfg=cfg,
        on_theme_changed=lambda: pytest.fail('unexpected preset apply')))
    before = theme_vector_style(state.theme).label_color
    w._set_color('map', 'label', '#ee88cc')
    assert theme_vector_style(state.theme, cfg['theme']).label_color == (238, 136, 204)
    assert state.contrast == 1.7
    w._revert()
    assert theme_vector_style(state.theme, cfg['theme']).label_color == before


def test_named_preset_restores_visual_options_and_colours():
    cfg = Config()
    state = MapState(cfg)
    w = ThemeWidget(WidgetContext(state=state, cfg=cfg))
    state.set_render_mode('braille')
    state.labels = False
    state.threshold_mode = 'fixed'
    state.shaded_blocks = True
    cfg.update({'render': {'geometry_mode': 'solid', 'detail_labels': False}})
    w._set_color('map', 'label', 'pink')
    w._set_color('map', 'road', '#aaccee')
    preview_roads = theme_vector_style(state.theme, cfg['theme']).road_colors
    expected = capture_settings(state, cfg)
    try:
        w._save_as('my test map')
        assert state.theme == 'my_test_map'
        assert T.vector_style_kwargs(state.theme)['label_color'] == (238, 154, 193)
        assert theme_vector_style(state.theme).road_colors == preview_roads
        state.set_render_mode('half')
        state.labels = True
        cfg.update({'render': {'geometry_mode': 'standard'}})
        apply_settings(state, cfg, T.theme_render('my_test_map'))
        assert capture_settings(state, cfg) == expected
        with pytest.raises(ValueError):
            w._save_as('my test map')
    finally:
        T.delete_user_theme('my_test_map')


@pytest.mark.parametrize('source', ['vector', 'raster'])
def test_preset_survives_config_reload(source, tmp_path):
    cfg = Config(path=str(tmp_path / 'profile.json'))
    state = MapState(cfg)
    state.set_source(source)
    state.set_render_mode('half')
    state.labels = False
    state.contrast = 1.3
    apply_settings(state, cfg, capture_settings(state, cfg))
    cfg.save()
    restored = MapState(Config.load(cfg.path))
    assert (restored.source, restored.render_mode, restored.labels, restored.contrast) == (source, 'half', False, 1.3)


def test_interface_colour_changes_visible_settings_style():
    from cartotui.themes import make_style
    cfg = Config()
    state = MapState(cfg)
    w = ThemeWidget(WidgetContext(state=state, cfg=cfg))
    w._set_color('ui', 'settings_bg', '#102030')
    assert make_style(cfg).get_attrs_for_style_str('class:settings').bgcolor == '102030'
