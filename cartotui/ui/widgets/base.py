from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

Run = Tuple[str, str]
Line = List[Run]
Hit = Tuple[int, int, int, Callable[[], None]]

@dataclass
class WidgetContext:
    state: Any = None
    cfg: Any = None
    map_control: Any = None
    aircraft_registry: Any = None
    get_traffic: Optional[Callable[[], Any]] = None
    on_theme_changed: Optional[Callable[[], None]] = None
    request_render: Optional[Callable[[], None]] = None
    invalidate: Optional[Callable[[], None]] = None
    snapshot: Optional[Callable[[str], None]] = None
    save_profile: Optional[Callable[[], None]] = None
    manager: Any = None

    def refresh(self) -> None:
        if self.invalidate is not None:
            self.invalidate()

    def rerender(self) -> None:
        if self.request_render is not None:
            self.request_render()
        self.refresh()

class Widget:
    name: str = "widget"
    title: str = "Widget"
    default_width: int = 30
    default_top: int = 2
    default_left: int = 2
    default_visible: bool = False

    def __init__(self, ctx: WidgetContext) -> None:
        self.ctx = ctx
        self._lines: List[Line] = []
        self._hits: List[Hit] = []

    def build(self, width: int) -> None:
        raise NotImplementedError

    def on_key(self, key: str) -> bool:
        return False

    def render_body(self, width: int) -> Tuple[List[Line], List[Hit]]:
        self._lines = []
        self._hits = []
        try:
            self.build(max(4, int(width)))
        except Exception:
            self._lines = [[("class:panel.warn", " (widget error)".ljust(width)[:width])]]
        return self._lines, self._hits

    def body_height(self, width: int) -> int:
        lines, _ = self.render_body(width)
        return max(1, len(lines))

    def _pad(self, s: str, width: int) -> str:
        return (s + " " * width)[:width]

    def add_text(self, s: str, width: int, style: str = "class:panel.value") -> None:
        self._lines.append([(style, self._pad(" " + s, width))])

    def add_dim(self, s: str, width: int) -> None:
        self.add_text(s, width, style="class:panel.dim")

    def add_blank(self, width: int) -> None:
        self._lines.append([("class:panel", " " * width)])

    def add_section(self, title: str, width: int) -> None:
        head = " " + title + " "
        fill = width - len(head)
        runs: Line = [("class:panel.section", head)]
        if fill > 0:
            runs.append(("class:panel.dim", "─" * fill))
        self._lines.append(runs)

    def add_kv(self, label: str, value: str, width: int,
               action: Optional[Callable[[], None]] = None,
               hot: Optional[str] = None) -> None:
        lbl = " " + label
        tail = f" [{hot}]" if hot else (" ▸" if action is not None else "")
        val = str(value)
        gap = width - len(lbl) - len(val) - len(tail)
        if gap < 1:
            keep = width - len(lbl) - len(tail) - 1
            val = val[:max(0, keep)]
            gap = max(1, width - len(lbl) - len(val) - len(tail))
        y = len(self._lines)
        runs: Line = [
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            ("class:panel.value", val),
        ]
        if tail:
            runs.append(("class:panel.hotkey" if action is not None else "class:panel.dim", tail))
        self._lines.append(runs)
        if action is not None:
            self._hits.append((y, 0, width, action))

    def add_button(self, label: str, width: int,
                   action: Callable[[], None], active: bool = False) -> None:
        cap = f"[ {label} ]"
        cap = self._pad(" " + cap, width)
        y = len(self._lines)
        style = "class:panel.title.active" if active else "class:panel.button"
        self._lines.append([(style, cap)])
        self._hits.append((y, 0, width, action))

    def add_swatch(self, label: str, hexcolor: str, width: int,
                   action: Optional[Callable[[], None]] = None) -> None:
        hexcolor = hexcolor if hexcolor.startswith("#") else "#" + hexcolor
        lbl = " " + label
        sw = "  ██  "
        val = hexcolor
        tail = " ▸" if action is not None else ""
        gap = width - len(lbl) - len(sw) - len(val) - len(tail)
        if gap < 1:
            gap = 1
        y = len(self._lines)
        runs: Line = [
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            (f"fg:{hexcolor}", sw),
            ("class:panel.value", val),
        ]
        if tail:
            runs.append(("class:panel.hotkey", tail))
        self._lines.append(runs)
        if action is not None:
            self._hits.append((y, 0, width, action))

    def add_adjust(self, label: str, value: str, width: int,
                   on_minus: Callable[[], None],
                   on_plus: Callable[[], None]) -> None:
        minus, plus = "[-]", "[+]"
        lbl = " " + label
        right = len(minus) + 1 + len(value) + 1 + len(plus)
        gap = max(1, width - len(lbl) - right)
        y = len(self._lines)
        self._lines.append([
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            ("class:panel.button", minus),
            ("class:panel", " "),
            ("class:panel.value", value),
            ("class:panel", " "),
            ("class:panel.button", plus),
        ])
        x = len(lbl) + gap
        self._hits.append((y, x, x + len(minus), on_minus))
        xp0 = x + len(minus) + 1 + len(value) + 1
        self._hits.append((y, xp0, xp0 + len(plus), on_plus))

    def add_row(self, runs: Line, width: int,
                action: Optional[Callable[[], None]] = None) -> None:
        y = len(self._lines)
        self._lines.append(list(runs))
        if action is not None:
            self._hits.append((y, 0, width, action))
