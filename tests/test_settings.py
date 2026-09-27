from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from cartotui.config import Config
from cartotui.ui.app import CartoTUIApp
from cartotui.ui.settings import PAGES


def make_app():
    cfg = Config()
    cfg.data["traffic"]["enabled"] = False
    cfg.data["vector"]["mvt_url"] = ""
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        return CartoTUIApp(cfg)


def test_every_page_fits_small_terminal_and_actions_scroll_into_view():
    app = make_app()
    try:
        menu = app.sidebar.control
        for page in ["home"] + [key for key, _ in PAGES]:
            menu.open_page(page)
            for width, height in ((28, 12), (44, 24), (60, 40)):
                content = menu.create_content(width, height)
                assert content.line_count <= height
                for y in range(content.line_count):
                    assert sum(len(run[1]) for run in content.get_line(y)) == width
                menu.move(10000)
                menu.create_content(width, height)
                if menu._actions:
                    assert any(
                        action is menu._actions[menu.selected][3] for _, _, _, action in menu._hits
                    )
    finally:
        app.map_control.shutdown()


def test_existing_widget_shortcuts_open_same_settings_window():
    app = make_app()
    try:
        app.widget_manager.toggle("render")
        assert app.sidebar.control.page == "render"
        assert app.app.layout.current_window is app.sidebar.window
        assert app.widget_manager.build_floats() == []
        app.sidebar.control.back()
        assert app.sidebar.control.page == "home"
        app.sidebar.control.back()
        assert not app.state.sidebar_visible
    finally:
        app.map_control.shutdown()


def test_keyboard_can_open_page_and_change_setting():
    app = make_app()
    try:
        menu = app.sidebar.control
        menu.open_page("home")
        menu.create_content(44, 20)
        menu.move(1)
        menu.activate()
        assert menu.page == "render"
        menu.create_content(44, 20)
        before = app.state.source
        menu.activate()
        assert app.state.source != before
    finally:
        app.map_control.shutdown()
