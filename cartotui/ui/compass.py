
from __future__ import annotations

from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl

from cartotui.ui.state import MapState

_ARROWS = [
    (0,   "↑"),
    (45,  "↗"),
    (90,  "→"),
    (135, "↘"),
    (180, "↓"),
    (225, "↙"),
    (270, "←"),
    (315, "↖"),
]

def _arrow_for(deg: float) -> str:
    deg = deg % 360
    return min(_ARROWS, key=lambda d: min(abs(d[0] - deg), 360 - abs(d[0] - deg)))[1]

def _compass_for(deg: float) -> str:
    deg = deg % 360
    if deg < 22.5 or deg >= 337.5:
        return "N"
    if deg < 67.5:
        return "NE"
    if deg < 112.5:
        return "E"
    if deg < 157.5:
        return "SE"
    if deg < 202.5:
        return "S"
    if deg < 247.5:
        return "SW"
    if deg < 292.5:
        return "W"
    return "NW"

class Compass(UIControl):
    def __init__(self, state: MapState):
        self.state = state

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        deg = self.state.heading_deg
        arrow = _arrow_for(deg)
        cardinal = _compass_for(deg)
        z = self.state.z

        rose_lines = [
            "  N    ",
            " ╲ │ ╱ ",
            f"W─ {arrow} ─E",
            " ╱ │ ╲ ",
            "  S    ",
        ]
        info_lines = [
            f"{cardinal:>2} {deg:03.0f}°",
            f"  z{z:02d}  ",
        ]

        all_lines = rose_lines + ["", *info_lines]

        def get_line(i: int):
            if 0 <= i < len(all_lines):
                line = all_lines[i]
                if len(line) < width:
                    line = line + " " * (width - len(line))
                else:
                    line = line[:width]
                if i == 2:
                    return to_formatted_text([
                        ("class:compass.label", line[:3]),
                        ("class:compass", line[3:5]),
                        ("class:compass.label", line[5:]),
                    ])
                if i == len(rose_lines) + 1:
                    return to_formatted_text([("class:compass", line)])
                if i == len(rose_lines) + 2:
                    return to_formatted_text([("class:compass.label", line)])
                return to_formatted_text([("class:compass.label", line)])
            return to_formatted_text([("class:compass.label", " " * width)])

        return UIContent(get_line=get_line, line_count=max(1, len(all_lines)))
