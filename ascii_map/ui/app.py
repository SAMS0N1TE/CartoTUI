#!/usr/bin/env python3
# ascii_map/ui/app.py
"""Compose the prompt_toolkit application for the ASCII map viewer."""

from prompt_toolkit.application import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from ascii_map.ui.state import MapState
from ascii_map.ui.map_control import MapControl
from ascii_map.ui.toolbar import Toolbar
from ascii_map.ui.statusbar import StatusBar
from ascii_map.ui.compass import Compass
from ascii_map.ui.helppane import HelpPane
from ascii_map.config import Config
from ascii_map.rendering.renderer import Renderer, default_palettes


class AsciiMapApp:
    def __init__(self):
        self.cfg = Config.load()
        self.state = MapState(self.cfg)
        self.renderer = Renderer(default_palettes())
        self.map_control = MapControl(self.cfg, self.state, self.renderer)
        self.status = StatusBar(self.state, self.cfg)
        self.compass = Compass(self.state)
        self.help_pane = HelpPane()
        self.toolbar = Toolbar(self.state, self.map_control, self.help_pane)

        # Layout: map stretches, compass stays narrow, accessories stack below.
        self.map_window = Window(
            content=self.map_control,
            dont_extend_width=False,
            wrap_lines=False,
        )
        self.map_control.bind_window(self.map_window)
        self.root = HSplit([
            VSplit([
                self.map_window,
                Window(content=self.compass, width=10),   # fixed width compass
            ], padding=1),
            self.toolbar,       # Use the container directly
            self.status,        # Use the container directly
            self.help_pane,     # height 0 when hidden
        ])

        self.kb = self._build_key_bindings()
        self.app = Application(
            layout=Layout(self.root, focused_element=self.map_window),
            key_bindings=self.kb,
            full_screen=True,
            style=Style.from_dict({
                "toolbar": "bg:#222222 #ffffff",
                "status": "bg:#333333 #cccccc",
                "compass": "fg:#00ff00 bold",
            }),
            mouse_support=True,
        )

    def _build_key_bindings(self):
        kb = KeyBindings()

        @kb.add("q")
        def _(event):
            event.app.exit()

        @kb.add("up")
        def _(event):
            self.map_control.pan(0, -1)

        @kb.add("down")
        def _(event):
            self.map_control.pan(0, 1)

        @kb.add("left")
        def _(event):
            self.map_control.pan(-1, 0)

        @kb.add("right")
        def _(event):
            self.map_control.pan(1, 0)

        @kb.add("=")
        def _(event):
            self.map_control.zoom(+1)

        @kb.add("-")
        def _(event):
            self.map_control.zoom(-1)

        @kb.add("h")
        def _(event):
            self.help_pane.toggle()
            event.app.invalidate()

        return kb

    def run(self):
        try:
            self.app.run()
        finally:
            self.map_control.shutdown()
