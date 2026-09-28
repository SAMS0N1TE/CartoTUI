"""One scrollable, keyboard-first home for settings and tools."""

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.controls import UIContent
from prompt_toolkit.mouse_events import MouseEventType

from cartotui.ui.sidebar import Sidebar, SidebarControl, _get_bc
from cartotui.ui.widgets.panel import Panel

PAGES = (
    ("looks", "Preset library"),
    ("render", "Map appearance"),
    ("theme", "Preset editor"),
    ("location", "Location"),
    ("radar", "Weather radar"),
    ("weather", "Weather"),
    ("adsb", "Aircraft settings"),
    ("traffic", "Live aircraft"),
    ("search", "Search"),
    ("performance", "Performance"),
    ("snapshot", "Export"),
    ("stats", "Statistics"),
    ("compass", "Compass"),
    ("widgets", "Movable windows"),
    ("help", "Keyboard help"),
)


class SettingsControl(SidebarControl):
    manager = None
    page = "home"
    selected = 0
    scroll = 0

    def open_page(self, page):
        self.page = page
        self.selected = self.scroll = 0
        self._actions = []
        self.state.sidebar_visible = True
        self.collapsed = False
        # A pasted or fast key sequence can arrive before the first redraw.
        # Navigation must have actions immediately, not depend on paint timing.
        self._body_length = len(self._body(self.width_chars))
        self._actions = list(self._hits)

    def set_tab(self, idx):
        self.open_page(("home", "search", "help", "traffic", "performance")[idx % 5])

    def cycle_tab(self, delta):
        pages = ["home"] + [key for key, _ in PAGES]
        self.open_page(pages[(pages.index(self.page) + delta) % len(pages)])

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return min(max_available_height, self.compact_height())

    def compact_height(self):
        # Layout asks repeatedly. Do not rebuild every widget just to size it.
        return getattr(self, "_body_length", 20) + 7

    def pop_out(self):
        if self.manager and self.manager.panel(self.page):
            self.manager.show(self.page)
            self._hide()

    def _body(self, width):
        self._hits = []
        if self.page == "home":
            lines = []
            for key, title in PAGES:
                group = {"looks": "Map", "radar": "Live layers", "search": "Tools"}.get(key)
                if group:
                    if lines:
                        lines.append([])
                    lines.append([("class:panel.section", " " + group.upper())])
                y = len(lines)
                lines.append([("class:panel.value", "  " + title.ljust(max(1, width - 4)) + " >")])
                self._hits.append((y, 0, width, lambda key=key: self.open_page(key)))
            if self.manager and self.manager.ctx.save_profile:
                lines.append([])
                self._hits.append((len(lines), 0, width, self.manager.ctx.save_profile))
                lines.append([("class:panel.button", " Save profile")])
            return lines
        if self.manager and self.manager.panel(self.page):
            lines, hits = self.manager.panel(self.page).widget.render_body(width)
            self._hits = list(hits) + [(len(lines) + 1, 0, width, self.pop_out)]
            return lines + [[], [("class:panel.button", " Open movable window >")]]
        bc = _get_bc(self.cfg)
        if self.page == "performance" and self.manager:
            lines, hits = self.manager.panel("render").widget.performance_body(width)
            self._hits = []
            extra = self._build_performance_lines(width, bc)
            self._hits = list(hits) + [(y + len(lines), x0, x1, fn)
                                      for y, x0, x1, fn in self._hits]
            return lines + extra
        builders = {
            "search": self._build_search_lines,
            "traffic": self._build_integration_lines,
            "performance": self._build_performance_lines,
            "help": self._build_controls_lines,
        }
        return builders[self.page](width, bc)

    def create_content(self, width, height):
        width = max(1, width)
        inner = max(1, width - 4)
        body = self._body(inner)
        self._body_length = len(body)
        self._actions = list(self._hits)
        self.selected = min(self.selected, max(0, len(self._actions) - 1))
        room = max(1, height - 7)
        if self._actions:
            row = self._actions[self.selected][0]
            if row < self.scroll:
                self.scroll = row
            elif row >= self.scroll + room:
                self.scroll = row - room + 1
        self.scroll = min(self.scroll, max(0, len(body) - room))
        title = dict(PAGES).get(self.page, "Settings")
        border = "class:settings.border"
        rule = [(border, "+" + "-" * max(0, width - 2) + "+")]

        def framed(line):
            fitted = [("class:settings " + style.replace("class:panel", "class:settings")
                     .replace("class:sidebar", "class:settings"), text)
                      for style, text in Panel._fit_line(line, inner)]
            return [(border, "|"), ("class:settings", " ")] + fitted + [
                ("class:settings", " "), (border, "|")]

        rows = [framed([("class:settings.title", title.upper())]),
                framed([("class:settings.title", "[ Back ]  [ Close ]")]), rule]
        self._hits = [(1, 2, min(10, width), self.back),
                      (1, 12, width - 1, self._hide)]
        for i, line in enumerate(body[self.scroll : self.scroll + room]):
            y = i + self.scroll
            line = Panel._fit_line(line, inner)
            if self._actions and y == self._actions[self.selected][0]:
                _, x0, x1, _ = self._actions[self.selected]
                highlighted = []
                x = 0
                for style, text in line:
                    for ch in text:
                        selected = x0 <= x < x1
                        if self.page == "home" and x == 0:
                            ch = ">"
                        highlighted.append(("class:settings.selected" if selected else style, ch))
                        x += 1
                line = highlighted
            rows.append(framed(line))
        while len(rows) < room + 3:
            rows.append(framed([]))
        for y, x0, x1, action in self._actions:
            if self.scroll <= y < self.scroll + room:
                self._hits.append((y - self.scroll + 3, x0 + 2, min(x1 + 2, width - 2), action))
        rows.extend([rule,
                     framed([("class:settings.dim", "Up/Down move  Enter act")]),
                     framed([("class:settings.hotkey", "Esc close  Left back"),
                             ("class:settings.dim", "   v" if self.scroll + room < len(body) else "")]),
                     rule])
        rows = [Panel._fit_line(line, width) for line in rows[:height]]
        return UIContent(get_line=lambda i: rows[i] if i < len(rows) else [], line_count=len(rows))

    def move(self, delta):
        actions = getattr(self, "_actions", [])
        if actions:
            self.selected = max(0, min(len(actions) - 1, self.selected + delta))
        else:
            self.scroll = max(0, self.scroll + delta)

    def activate(self):
        actions = getattr(self, "_actions", [])
        if actions:
            actions[self.selected][3]()
            self._body(self.width_chars)
            self._actions = list(self._hits)
            self.selected = min(self.selected, max(0, len(self._actions) - 1))
        elif self.page == "search":
            self.search_submit()

    def back(self):
        if self.page != "home":
            self.open_page("home")
        else:
            self._hide()

    def mouse_handler(self, ev):
        if ev.event_type == MouseEventType.SCROLL_DOWN:
            self.move(1)
        elif ev.event_type == MouseEventType.SCROLL_UP:
            self.move(-1)
        elif ev.event_type == MouseEventType.MOUSE_UP:
            for y, x0, x1, action in self._hits:
                if y == ev.position.y and x0 <= ev.position.x < x1:
                    action()
                    break
        return None


class SettingsSidebar(Sidebar):
    control_type = SettingsControl

    def keybindings(self):
        kb = KeyBindings()
        for key, action in (
            ("up", lambda: self.control.move(-1)),
            ("down", lambda: self.control.move(1)),
            ("pageup", lambda: self.control.move(-8)),
            ("pagedown", lambda: self.control.move(8)),
            ("enter", self.control.activate),
            ("escape", self.control._hide),
            ("left", self.control.back),
            ("right", self.control.activate),
        ):
            kb.add(key, eager=(key == "escape"))(lambda event, action=action: action())

        @kb.add("backspace")
        def backspace(event):
            if self.control.page == "search":
                self.control.search_backspace()
            else:
                self.control.back()

        @kb.add("<any>")
        def text(event):
            if self.control.page == "search" and event.data.isprintable():
                self.control.search_keystroke(event.data)

        return kb
