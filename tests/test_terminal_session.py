"""Exercise VT100 output and keyboard input with no mouse or graphics protocol."""

import asyncio
import io

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.output.vt100 import Vt100_Output

from cartotui.config import Config
from cartotui.ui.app import CartoTUIApp
from cartotui.ui.map_control import _Frame


@pytest.mark.parametrize("direct, packed", [(False, False), (True, False), (True, True)])
def test_keyboard_settings_over_vt100(direct, packed):
    async def run():
        stream = io.StringIO()
        output = Vt100_Output(
            stream,
            lambda: Size(rows=24, columns=80),
            term="xterm-256color",
            enable_cpr=False,
            default_color_depth=ColorDepth.DEPTH_8_BIT,
        )
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=output):
            cfg = Config()
            cfg.data["ui"]["mouse"] = False
            cfg.data["viewport"]["show_sidebar"] = False
            cfg.data["render"]["color_depth"] = "256"
            app = CartoTUIApp(cfg)
            app.map_control._enqueue = lambda *args, **kwargs: None
            app.map_control.request_render = lambda *args, **kwargs: None
            app.map_control._last_frame = _Frame(
                80, 20, [[("fg:#20386a bg:#000000", "▀" * 80)] for _ in range(20)], ()
            )
            if direct:
                app._install_direct_paint()
            task = asyncio.create_task(app.app.run_async())

            async def until(predicate):
                for _ in range(100):
                    if predicate():
                        return
                    await asyncio.sleep(0.02)
                raise AssertionError("terminal interaction did not complete")

            try:
                await until(lambda: app.app.is_running)
                if packed:
                    import numpy as np

                    from cartotui.rendering.packed import PackedFrame
                    w, h = app.map_control._last_w, app.map_control._last_h
                    cells = PackedFrame(np.full((h,w), 0x2580, np.uint32),
                                        np.full((h,w), 0x20386a, np.uint32),
                                        np.zeros((h,w), np.uint32), w, h)
                    app.map_control._last_frame = _Frame(w, h, cells, ())
                    app.app.invalidate()
                    await until(lambda: hasattr(app.app.renderer, "_native_encoder"))
                pipe.send_text("w")
                await until(lambda: app.state.sidebar_visible)
                await until(lambda: bool(getattr(app.sidebar.control, "_actions", [])))
                pipe.send_text("\x1b[B\r")
                await until(lambda: app.sidebar.control.page == "render")
                await until(lambda: "MAP APPEARANCE" in stream.getvalue())
                before = app.state.render_mode
                pipe.send_text("m")
                await until(lambda: app.state.render_mode != before)
                assert app.state.sidebar_visible
                before = app.state.palette
                pipe.send_text("p")
                await until(lambda: app.state.palette != before)
                app.sidebar.control.open_page("search")
                before = app.state.render_mode
                pipe.send_text("m")
                await until(lambda: app.sidebar.control.search_text.endswith("m"))
                assert app.state.render_mode == before
                started = asyncio.get_running_loop().time()
                pipe.send_text("\x1b")
                await until(lambda: not app.state.sidebar_visible)
                assert asyncio.get_running_loop().time() - started < 0.4
                pipe.send_text("\x03")
                await asyncio.wait_for(task, 3)
                assert "38;2;" not in stream.getvalue()
                assert "38;5;" in stream.getvalue()
                assert "\x1b_G" not in stream.getvalue()  # no Kitty protocol
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                app.map_control.shutdown()
                app.vector_source.close()

    asyncio.run(run())


def test_colour_and_name_dialogs_accept_keyboard_over_vt100():
    from cartotui import theme_loader as T
    from cartotui.ui.widgets.input_dialog import ask_text
    from prompt_toolkit.application.current import set_app

    async def run():
        output = Vt100_Output(io.StringIO(), lambda: Size(rows=30, columns=90), enable_cpr=False)
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=output):
            app = CartoTUIApp(Config())
            app.map_control._enqueue = lambda *a, **k: None
            app.map_control.request_render = lambda *a, **k: None
            task = asyncio.create_task(app.app.run_async())
            async def until(predicate):
                for _ in range(100):
                    if predicate():
                        return
                    await asyncio.sleep(.02)
                raise AssertionError('dialog did not complete')
            try:
                await until(lambda: app.app.is_running)
                editor = app.widget_manager.panel('theme').widget
                with set_app(app.app):
                    ask_text(editor.ctx, 'Label colour', 'Hex or name', '',
                             lambda value: editor._set_color('map', 'label', value))
                pipe.send_text('#55ccaa\r')
                await until(lambda: app.cfg['theme'].get('label') == '#55ccaa')
                with set_app(app.app):
                    editor._duplicate()
                pipe.send_text('Keyboard Map\r')
                await until(lambda: app.state.theme == 'keyboard_map')
                assert T.vector_style_kwargs('keyboard_map')['label_color'] == (85, 204, 170)
                # Typing q into a modal field must not quit the map application.
                with set_app(app.app):
                    editor._duplicate()
                pipe.send_text('q')
                await asyncio.sleep(.08)
                assert not task.done()
                pipe.send_text('\x1b')
                await asyncio.sleep(.6)
                app.app.exit()
                await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                T.delete_user_theme('keyboard_map')
                app.map_control.shutdown()
                app.vector_source.close()
                app.radar_source.close()
    asyncio.run(run())
