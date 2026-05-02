
from __future__ import annotations

from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl

from cartotui import __version__
from cartotui.ui.state import MapState

class TitleBar(UIControl):
    def __init__(self, state: MapState, title: str = "CartoTUI") -> None:
        self.state = state
        self.title = title

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        left = f"  {self.title} v{__version__}  "
        coords = (f"{self.state.lat:>+9.4f}°, {self.state.lon:>+10.4f}°"
                  f"  z{self.state.z:02d}")
        right = "  "

        gap_total = max(0, width - len(left) - len(coords) - len(right))
        gap_l = gap_total // 2
        gap_r = gap_total - gap_l

        runs = [
            ("class:titlebar",     left),
            ("class:titlebar.dim", " " * gap_l),
            ("class:titlebar",     coords),
            ("class:titlebar.dim", " " * gap_r),
            ("class:titlebar",     right),
        ]

        rendered = "".join(text for _s, text in runs)
        if len(rendered) > width:
            rendered = rendered[:width]
            runs = [("class:titlebar", rendered)]
        elif len(rendered) < width:
            runs.append(("class:titlebar.dim", " " * (width - len(rendered))))

        formatted = to_formatted_text(runs)
        return UIContent(
            get_line=lambda i: formatted if i == 0 else [("class:titlebar", " " * width)],
            line_count=1,
        )
