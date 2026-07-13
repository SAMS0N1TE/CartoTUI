
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui import __version__
from cartotui.ui.state import MapState


class TitleBar(UIControl):
    def __init__(self, state: MapState, title: str = "CartoTUI",
                 on_snapshot: Optional[Callable[[str], None]] = None) -> None:
        self.state = state
        self.title = title
        self.on_snapshot = on_snapshot
        self._hits: List[Tuple[int, int, str]] = []

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        left = f"  {self.title} v{__version__}  "
        coords = (f"{self.state.lat:>+9.4f}°, {self.state.lon:>+10.4f}°"
                  f"  z{self.state.z:02d}")
        png, htm = "[PNG]", "[HTML]"
        btns_len = len(png) + 1 + len(htm) + 1

        avail = max(0, width - len(left) - btns_len)
        if len(coords) > avail:
            coords = coords[:avail]
        pad_total = avail - len(coords)
        pad_l = pad_total // 2
        pad_r = pad_total - pad_l

        png_x0 = len(left) + pad_l + len(coords) + pad_r
        htm_x0 = png_x0 + len(png) + 1
        self._hits = [
            (png_x0, png_x0 + len(png), "png"),
            (htm_x0, htm_x0 + len(htm), "html"),
        ]

        runs = [
            ("class:titlebar",     left),
            ("class:titlebar.dim", " " * pad_l),
            ("class:titlebar",     coords),
            ("class:titlebar.dim", " " * pad_r),
            ("class:titlebar.hotkey", png),
            ("class:titlebar.dim", " "),
            ("class:titlebar.hotkey", htm),
            ("class:titlebar.dim", " "),
        ]

        formatted = to_formatted_text(runs)
        return UIContent(
            get_line=lambda i: formatted if i == 0 else [("class:titlebar", " " * width)],
            line_count=1,
        )

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type != MouseEventType.MOUSE_UP:
            return NotImplemented
        x = mouse_event.position.x
        for (x0, x1, kind) in self._hits:
            if x0 <= x < x1:
                if self.on_snapshot is not None:
                    self.on_snapshot(kind)
                app = get_app_or_none()
                if app:
                    app.invalidate()
                return None
        return NotImplemented
