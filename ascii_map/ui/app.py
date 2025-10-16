#!/usr/bin/env python3
# ascii_map/ui/app.py
"""
Main TUI application assembly using prompt_toolkit.

This initializes:
- Layout (map view, toolbar, statusbar, compass, help)
- Key bindings and clickable toolbar buttons
- Application run loop and refresh logic
"""

import asyncio, time
from prompt_toolkit.application import Application, get_app
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Label

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
        self.toolbar = Toolbar(self.state, self.map_control)
        self.status = StatusBar(self.state, self.cfg)
        self.compass = Compass(self.state)
        self.help_pane = HelpPane()

        # Layout: stable heights; map expands.
        self.root = HSplit([
            VSplit([
                Window(content=self.map_control, dont_extend_width=False),
                Window(content=self.compass, width=10),   # fixed width compass
            ], padding=1),
            self.toolbar,       # Use the container directly
            self.status,        # Use the container directly
            self.help_pane,     # height 0 when hidden
        ])


        self.kb = self._build_key_bindings()
        self.app = Application(
            layout=Layout(self.root),
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
        def _(e): e.app.exit()

        @kb.add("up")
        def _(e): self.map_control.pan(0, -1)

        @kb.add("down")
        def _(e): self.map_control.pan(0, 1)

        @kb.add("left")
        def _(e): self.map_control.pan(-1, 0)

        @kb.add("right")
        def _(e): self.map_control.pan(1, 0)

        @kb.add("=")
        def _(e): self.map_control.zoom(+1)

        @kb.add("-")
        def _(e): self.map_control.zoom(-1)

        @kb.add("h")
        def _(e): self.help_pane.toggle()

        return kb

    def run(self):
        self.app.run()