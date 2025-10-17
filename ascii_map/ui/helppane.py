#!/usr/bin/env python3
# ascii_map/ui/helppane.py

from __future__ import annotations

from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.widgets import Frame, TextArea

_HELP_TEXT = (
    "Key Bindings:\n"
    "  ↑ ↓ ← →   Move map\n"
    "  + / -     Zoom in/out\n"
    "  h         Toggle this help\n"
    "  q         Quit\n"
    "\n"
    "Mouse:\n"
    "  Click toolbar buttons to pan/zoom\n"
    "\n"
    "Info:\n"
    "  Compass shows last pan direction.\n"
    "  Status bar displays render timing and position.\n"
)


class HelpPane:
    def __init__(self):
        self._visible = False
        self.text_area = TextArea(
            text=_HELP_TEXT,
            style="class:help",
            read_only=True,
            focusable=False,
        )
        self.frame = Frame(self.text_area, title="Help", style="class:help")
        self.container = HSplit([self.frame])

    def __pt_container__(self):
        return self.container if self._visible else Window(height=0)

    def toggle(self) -> None:
        self._visible = not self._visible
