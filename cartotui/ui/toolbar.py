
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui.ui.map_control import MapControl
from cartotui.ui.state import MapState

_TOOLBAR_ITEMS: List[Tuple[str, str]] = [
    ("Q",   "Quit"),
    ("?",   "Help"),
    ("+/-", "Zoom"),
    ("K",   "Style"),
    ("V",   "Src"),
    ("M",   "View"),
    ("T",   "Theme"),
    ("P",   "Pal"),
    ("D",   "Dith"),
    ("S",   "Shade"),
    ("U",   "Thr"),
    ("C",   "Color"),
    ("G",   "Goto"),
    ("R",   "Reset"),
]

_SEP = "  "

def _is_disabled(state, key: str) -> bool:
    rm = state.render_mode
    if key == "D":
        return rm != "ascii"
    if key == "S":
        return rm == "ascii"
    return False

class Toolbar(UIControl):
    def __init__(
        self,
        state: MapState,
        map_control: MapControl,
        on_help: Callable[[], None],
        on_quit: Callable[[], None],
        on_goto: Callable[[], None],
        palettes: List[str],
        on_theme_changed: Optional[Callable[[], None]] = None,
        on_cycle_source: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state = state
        self.map_control = map_control
        self.on_help = on_help
        self.on_quit = on_quit
        self.on_goto = on_goto
        self.palettes = palettes
        self.on_theme_changed = on_theme_changed
        self.on_cycle_source = on_cycle_source

        self._hit_zones: List[Tuple[int, int, str]] = []

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        runs = []
        zones: List[Tuple[int, int, str]] = []
        col = 0

        runs.append(("class:toolbar", "  "))
        col += 2

        for idx, (key, label) in enumerate(_TOOLBAR_ITEMS):
            disabled = _is_disabled(self.state, key)
            key_cls  = "class:toolbar.dim" if disabled else "class:toolbar.key"
            text_cls = "class:toolbar.dim" if disabled else "class:toolbar"

            zone_start = col
            runs.append((key_cls, key))
            col += len(key)
            runs.append((text_cls, " " + label))
            col += len(label) + 1
            zones.append((zone_start, col, key))

            if idx < len(_TOOLBAR_ITEMS) - 1:
                runs.append(("class:toolbar.dim", _SEP))
                col += len(_SEP)

        if col < width:
            runs.append(("class:toolbar", " " * (width - col)))
        elif col > width:
            rendered = "".join(t for _s, t in runs)
            runs = [("class:toolbar", rendered[:width])]

        self._hit_zones = zones
        formatted = to_formatted_text(runs)
        return UIContent(
            get_line=lambda i: formatted if i == 0 else [("class:toolbar", " " * width)],
            line_count=1,
        )

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type != MouseEventType.MOUSE_UP:
            return None
        x = mouse_event.position.x
        for start, end, key in self._hit_zones:
            if start <= x < end:
                self._dispatch(key)
                return None
        return None

    def _dispatch(self, key: str) -> None:
        if _is_disabled(self.state, key):
            reason = self._disabled_reason(key)
            self.state.set_info(reason)
            app = get_app_or_none()
            if app:
                app.invalidate()
            return

        if key == "Q":
            self.on_quit()
        elif key == "?":
            self.on_help()
        elif key == "+/-":
            self.map_control.zoom(+1)
        elif key == "K":
            if self.on_cycle_source is not None:
                self.on_cycle_source()
        elif key == "V":
            self.state.toggle_source()
            self.state.set_info(f"Source → {self.state.source}")
            self.map_control.request_render()
        elif key == "M":
            self.state.cycle_render_mode()
            self.state.set_info(f"View → {self.state.render_mode}")
            self.map_control.request_render()
        elif key == "T":
            self.state.cycle_theme()
            self.state.set_info(f"Theme → {self.state.theme}")
            if self.on_theme_changed is not None:
                self.on_theme_changed()
        elif key == "P":
            self.state.cycle_palette(self.palettes)
            self.state.set_info(f"Palette → {self.state.palette}")
            self.map_control.request_render()
        elif key == "D":
            self.state.cycle_dither()
            self.state.set_info(f"Dither → {self.state.dither}")
            self.map_control.request_render()
        elif key == "S":
            self.state.toggle_shaded()
            self.state.set_info(f"Shaded {'on' if self.state.shaded_blocks else 'off'}")
            self.map_control.request_render()
        elif key == "U":
            self.state.cycle_threshold()
            self.state.set_info(f"Threshold → {self.state.threshold_mode}")
            self.map_control.request_render()
        elif key == "C":
            self.state.toggle_color()
            self.state.set_info(f"Color {'on' if self.state.color else 'off'}")
            self.map_control.request_render()
        elif key == "G":
            self.on_goto()
        elif key == "R":
            self.map_control.goto(
                float(self.state.cfg["map"]["center_lat"]),
                float(self.state.cfg["map"]["center_lon"]),
                int(self.state.cfg["map"]["zoom"]),
            )
        app = get_app_or_none()
        if app:
            app.invalidate()

    def _disabled_reason(self, key: str) -> str:
        if key == "D":
            return "Dither only applies in ASCII view"
        if key == "S":
            return "Shade only applies in quadrant/braille"
        return f"{key} not available"
