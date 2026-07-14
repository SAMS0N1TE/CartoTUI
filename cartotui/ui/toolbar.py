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

_MOVE = getattr(MouseEventType, "MOUSE_MOVE", None)


def _is_disabled(state, key: str) -> bool:
    rm = state.render_mode
    if key == "D":
        return rm != "ascii"
    if key == "S":
        return rm == "ascii"
    return False


def _clip_runs(runs, width):
    out = []
    used = 0
    for style, text in runs:
        if used >= width:
            break
        if used + len(text) > width:
            text = text[: width - used]
        if text:
            out.append((style, text))
            used += len(text)
    if used < width:
        out.append(("class:toolbar", " " * (width - used)))
    return out


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
        self._hover_key: Optional[str] = None
        self._press_key: Optional[str] = None

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        w = max(4, width)
        runs = []
        zones: List[Tuple[int, int, str]] = []
        col = 0
        runs.append(("class:toolbar", " "))
        col += 1

        for key, label in _TOOLBAR_ITEMS:
            disabled = _is_disabled(self.state, key)
            pressed = (not disabled) and self._press_key == key
            hover = (not disabled) and not pressed and self._hover_key == key
            if disabled:
                box = kc = lc = "class:toolbar.dim"
            elif pressed:
                box = kc = lc = "class:toolbar.key reverse bold"
            elif hover:
                box = kc = lc = "class:toolbar reverse"
            else:
                box, kc, lc = "class:toolbar.dim", "class:toolbar.key", "class:toolbar"

            zs = col
            runs.append((box, "["))
            runs.append((kc, key))
            runs.append((lc, " " + label))
            runs.append((box, "]"))
            col += 1 + len(key) + 1 + len(label) + 1
            zones.append((zs, col, key))
            runs.append(("class:toolbar", " "))
            col += 1

        self._hit_zones = zones
        formatted = to_formatted_text(_clip_runs(runs, w))
        return UIContent(
            get_line=lambda i: formatted if i == 0 else [("class:toolbar", " " * w)],
            line_count=1,
        )

    def _key_at(self, x: int) -> Optional[str]:
        for (x0, x1, key) in self._hit_zones:
            if x0 <= x < x1:
                return key
        return None

    def mouse_handler(self, mouse_event: MouseEvent):
        et = mouse_event.event_type
        key = self._key_at(mouse_event.position.x)
        changed = False

        if et == MouseEventType.MOUSE_DOWN:
            if self._press_key != key:
                self._press_key = key
                changed = True
        elif et == MouseEventType.MOUSE_UP:
            self._press_key = None
            changed = True
            if key is not None:
                self._dispatch(key)
                return None
        elif _MOVE is not None and et == _MOVE:
            if self._hover_key != key:
                self._hover_key = key
                changed = True

        if changed:
            app = get_app_or_none()
            if app:
                app.invalidate()
        return None

    def _dispatch(self, key: str) -> None:
        if _is_disabled(self.state, key):
            self.state.set_info(self._disabled_reason(key))
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
