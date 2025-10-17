#!/usr/bin/env python3
# ascii_map/ui/toolbar.py

from __future__ import annotations

from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.widgets import Box, Button, Label

from ascii_map.ui.helppane import HelpPane
from ascii_map.ui.map_control import MapControl
from ascii_map.ui.state import MapState


class Toolbar:
    """Clickable controls for panning, zooming, and toggling help."""

    def __init__(self, state: MapState, map_control: MapControl, help_pane: HelpPane):
        self.state = state
        self.map_control = map_control
        self.help_pane = help_pane

        self.btn_left = Button(text="←", handler=lambda: self._pan(-1, 0))
        self.btn_up = Button(text="↑", handler=lambda: self._pan(0, -1))
        self.btn_down = Button(text="↓", handler=lambda: self._pan(0, 1))
        self.btn_right = Button(text="→", handler=lambda: self._pan(1, 0))

        self.btn_zoom_out = Button(text="-", handler=lambda: self._zoom(-1))  # ASCII hyphen
        self.btn_zoom_in = Button(text="+", handler=lambda: self._zoom(+1))

        self.btn_help = Button(text="Help (h)", handler=self._help)
        self.btn_quit = Button(text="Quit (q)", handler=self._quit)

        self._container = Box(
            body=HSplit(
                [
                    Label("Toolbar  Click buttons or use keys"),
                    VSplit(
                        [
                            Label("Pan:"),
                            self.btn_left,
                            self.btn_up,
                            self.btn_down,
                            self.btn_right,
                            Window(width=1, char="|"),
                            Label("Zoom:"),
                            self.btn_zoom_out,
                            self.btn_zoom_in,
                            Window(width=1, char="|"),
                            self.btn_help,
                            self.btn_quit,
                        ],
                        padding=1,
                    ),
                ]
            ),
            style="class:toolbar",
            padding=1,
            height=3,
        )

    def __pt_container__(self):
        return self._container

    def _pan(self, dx: int, dy: int) -> None:
        self.map_control.pan(dx, dy)
        self.map_control.focus()

    def _zoom(self, delta: int) -> None:
        self.map_control.zoom(delta)
        self.map_control.focus()

    def _help(self) -> None:
        self.help_pane.toggle()
        self.state.set_info("Help toggled")
        app = get_app()
        app.invalidate()
        self.map_control.focus()

    def _quit(self) -> None:
        get_app().exit()
