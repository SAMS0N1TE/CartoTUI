#!/usr/bin/env python3
# ascii_map/ui/compass.py

from __future__ import annotations

from prompt_toolkit.formatted_text import HTML, to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl

from ascii_map.ui.state import MapState


class Compass(UIControl):
    def __init__(self, state: MapState):
        self.state = state

    def create_content(self, width: int, height: int) -> UIContent:
        ang = self.state.heading_deg
        text = HTML(f"{self._heading_to_arrow(ang)} {ang:03.0f}°")

        def get_line(_: int):
            return to_formatted_text(text)

        return UIContent(get_line=get_line, line_count=1)

    def is_focusable(self) -> bool:
        return False

    @staticmethod
    def _heading_to_arrow(deg: float) -> str:
        dirs = [
            (0, "↑N"),
            (45, "↗NE"),
            (90, "→E"),
            (135, "↘SE"),
            (180, "↓S"),
            (225, "↙SW"),
            (270, "←W"),
            (315, "↖NW"),
        ]
        return min(dirs, key=lambda d: abs(d[0] - (deg % 360)))[1]
