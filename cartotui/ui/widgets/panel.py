from __future__ import annotations

from typing import List, Optional, Tuple

from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui.themes import border_chars
from cartotui.ui.widgets.base import Widget

Hit = Tuple[int, int, int, object]


class Panel(UIControl):
    def __init__(self, widget: Widget, manager, top: int, left: int,
                 width: int, collapsed: bool = False) -> None:
        self.widget = widget
        self.manager = manager
        self.top = int(top)
        self.left = int(left)
        self.width = max(16, int(width))
        self.collapsed = bool(collapsed)
        self._hits: List[Hit] = []
        self._dragging = False
        self._grab: Optional[Tuple[int, int]] = None
        self._moved = False
        self.float = None
        self.window = Window(content=self, width=self.width, style="class:panel")

    @property
    def name(self) -> str:
        return getattr(self.widget, "name", "widget")

    def _bc(self) -> dict:
        cfg = self.manager.ctx.cfg
        theme = cfg["ui"].get("theme", "amber")
        style = cfg["ui"].get("border_style", "heavy")
        return border_chars(style, theme)

    def body_height(self) -> int:
        if self.collapsed:
            return 0
        inner = self.width - 2
        try:
            h = self.widget.body_height(inner)
        except Exception:
            h = 1
        return max(1, min(40, h))

    def height(self) -> int:
        if self.collapsed:
            return 1
        return self.body_height() + 2

    def is_focusable(self) -> bool:
        return True

    def preferred_width(self, max_available_width: int) -> int:
        return min(self.width, max_available_width)

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return min(self.height(), max_available_height)

    def _title_row(self, width: int, bc: dict) -> Tuple[list, list]:
        tl, tr, h = bc["tl"], bc["tr"], bc["h"]
        collapse = "[+]" if self.collapsed else "[-]"
        close = "[x]"
        suffix = collapse + close + tr
        title = self.widget.title
        prefix = tl + h + " " + title + " "
        pad = width - len(prefix) - len(suffix)
        if pad < 0:
            keep = max(0, len(title) + pad)
            title = title[:keep]
            prefix = tl + h + " " + title + " "
            pad = max(0, width - len(prefix) - len(suffix))
        col_x0 = width - len(suffix)
        close_x0 = col_x0 + len(collapse)
        runs = [
            ("class:panel.title", prefix + h * pad),
            ("class:panel.button", collapse),
            ("class:panel.button", close),
            ("class:panel.title", tr),
        ]
        btn_hits = [
            (0, col_x0, col_x0 + len(collapse), self._toggle_collapse),
            (0, close_x0, close_x0 + len(close), self._hide),
        ]
        return runs, btn_hits

    @staticmethod
    def _fit_line(line: list, inner: int) -> list:
        """Pad or clip a run list to exactly `inner` visible cells so the right
        border always lands at the panel edge (widgets may emit short rows)."""
        total = sum(len(t) for _, t in line)
        if total == inner:
            return list(line)
        if total < inner:
            return list(line) + [("class:panel", " " * (inner - total))]
        out: list = []
        used = 0
        for st, t in line:
            if used >= inner:
                break
            take = inner - used
            if len(t) <= take:
                out.append((st, t))
                used += len(t)
            else:
                out.append((st, t[:take]))
                used = inner
                break
        return out

    def create_content(self, width: int, height: int) -> UIContent:
        width = self.width
        bc = self._bc()
        v = bc["v"]
        inner = width - 2
        rows: List[list] = []
        self._hits = []

        title_runs, btn_hits = self._title_row(width, bc)
        rows.append(title_runs)
        self._hits.extend(btn_hits)

        if not self.collapsed:
            body_lines, body_hits = self.widget.render_body(inner)
            body_rows = max(1, height - 2)
            for i in range(body_rows):
                if i < len(body_lines):
                    line = self._fit_line(body_lines[i], inner)
                else:
                    line = [("class:panel", " " * inner)]
                rows.append([("class:panel.border", v)] + line + [("class:panel.border", v)])
            for (hy, x0, x1, fn) in body_hits:
                if hy < body_rows:
                    self._hits.append((hy + 1, x0 + 1, x1 + 1, fn))
            bottom = bc["bl"] + bc["h"] * inner + bc["br"]
            rows.append([("class:panel.border", bottom)])

        formatted = [to_formatted_text(r) for r in rows]

        def get_line(i: int):
            if 0 <= i < len(formatted):
                return formatted[i]
            return to_formatted_text([("class:panel", " " * width)])

        return UIContent(get_line=get_line, line_count=max(1, len(formatted)))

    def _hit_at(self, x: int, y: int):
        for (hy, x0, x1, fn) in self._hits:
            if hy == y and x0 <= x < x1:
                return fn
        return None

    def _toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self.manager.invalidate()
        self.manager.save_layout()

    def _hide(self) -> None:
        self._dragging = False
        self._grab = None
        self.manager.hide(self.name)

    def mouse_handler(self, ev: MouseEvent):
        x, y = ev.position.x, ev.position.y
        et = ev.event_type

        if et == MouseEventType.MOUSE_DOWN:
            self._moved = False
            if y == 0 and self._hit_at(x, 0) is None:
                self.manager.begin_drag(self, x, y)
            else:
                self.manager.end_drag(save=False)
                self.manager.bring_to_front(self)
            return None

        if et == MouseEventType.MOUSE_MOVE:
            if self.manager.is_dragging():
                self.manager.drag_to(self.left + x, self.top + y)
                self._moved = True
            return None

        if et == MouseEventType.MOUSE_UP:
            if self.manager.is_dragging():
                self.manager.end_drag()
            elif not self._moved:
                fn = self._hit_at(x, y)
                if fn is not None:
                    fn()
            return None

        return NotImplemented
