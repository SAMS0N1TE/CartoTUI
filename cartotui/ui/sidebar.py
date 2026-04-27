"""Right-edge tabbed sidebar.

Four tabs:

  * **Settings** — theme, palette, render mode, dither, color, threshold,
    brightness, contrast. The values shown are live and reflect ``MapState``.
  * **Search** — text input that resolves to lat/lon. Recent goto history.
  * **Controls** — quick-reference of keys + a small compass.
  * **Integration** — LandShark/SBS-1 connection status + aircraft list +
    selected-aircraft details.

Tabs are switched by ``[`` and ``]`` (prev / next) when the sidebar is
focused, or by their leading hotkey number ``1..4``. Toggle the sidebar
itself with ``Tab`` (or whatever the app keybinding maps).

The sidebar is a regular ``UIControl`` so it lives in any HSplit/VSplit
layout. It does *not* hold focus by default — it only focuses when the
user activates it (that's the app's job, not ours).
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Tuple

from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui.config import Config
from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import LinkStatus, TrafficSource
from cartotui.ui.state import MapState


SIDEBAR_TABS: Tuple[str, ...] = ("Settings", "Search", "Controls", "Integration")


# Public sentinel — index ↔ name lookups.
TAB_SETTINGS = 0
TAB_SEARCH = 1
TAB_CONTROLS = 2
TAB_INTEGRATION = 3


class SidebarControl(UIControl):
    """Renders the sidebar body. Mouse clicks on tab labels and aircraft rows
    are intercepted via a small per-frame hitmap that ``mouse_handler``
    consults."""

    def __init__(
        self,
        state: MapState,
        cfg: Config,
        get_traffic: Callable[[], Optional[TrafficSource]],
        get_registry: Callable[[], Optional[AircraftRegistry]],
        on_select_aircraft: Callable[[Optional[str]], None],
        on_search_submit: Callable[[str], None],
        width_chars: int,
    ) -> None:
        self.state = state
        self.cfg = cfg
        self.get_traffic = get_traffic
        self.get_registry = get_registry
        self.on_select_aircraft = on_select_aircraft
        self.on_search_submit = on_search_submit
        self.width_chars = max(28, int(width_chars))

        # Hitmap built each frame: list of (y, x0, x1, action)
        # action is a callable; mouse handler invokes it on click.
        self._hits: List[Tuple[int, int, int, Callable[[], None]]] = []

        # Search field state — owned by the sidebar so the Search tab can
        # type into it without needing a separate full prompt_toolkit
        # buffer. Returns are picked up by app to dispatch a goto.
        self.search_text: str = ""
        self.search_focused: bool = False

        # Cached scroll offset for aircraft list (page through with up/down
        # when sidebar is focused on Integration tab).
        self.aircraft_scroll: int = 0

    # ------------------------------------------------------------------
    # UIControl interface
    # ------------------------------------------------------------------

    def is_focusable(self) -> bool:
        return True

    def preferred_width(self, max_available_width: int) -> int:
        return min(self.width_chars, max_available_width)

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return max_available_height

    # ------------------------------------------------------------------
    # Tab switching helpers (called by app keybindings too)
    # ------------------------------------------------------------------

    def set_tab(self, idx: int) -> None:
        idx = max(0, min(len(SIDEBAR_TABS) - 1, int(idx)))
        self.state.sidebar_tab = idx
        self.aircraft_scroll = 0

    def cycle_tab(self, delta: int) -> None:
        self.set_tab((self.state.sidebar_tab + delta) % len(SIDEBAR_TABS))

    # ------------------------------------------------------------------
    # Body builders — one per tab
    # ------------------------------------------------------------------

    def _build_settings_lines(self, w: int) -> List:
        s = self.state
        lines = []
        lines.append(self._section("Display", w))
        lines.append(self._kv("Theme", s.theme, w, hot="t"))
        lines.append(self._kv("Palette", s.palette, w, hot="p"))
        lines.append(self._kv("Render", s.render_mode, w, hot="m"))
        lines.append(self._kv("Source", s.source, w, hot="v"))
        lines.append(self._kv("Color", "on" if s.color else "off", w, hot="c"))
        lines.append(self._kv("Dither", s.dither, w, hot="d"))
        lines.append(self._kv("Shaded", "on" if s.shaded_blocks else "off", w, hot="s"))
        lines.append(self._spacer(w))
        lines.append(self._section("Image", w))
        lines.append(self._kv("Threshold", s.threshold_mode, w, hot="u"))
        lines.append(self._kv("Brightness", f"{s.brightness:+.2f}", w, hot="[ ]"))
        lines.append(self._kv("Contrast", f"{s.contrast:+.2f}", w, hot="{ }"))
        lines.append(self._spacer(w))
        lines.append(self._section("View", w))
        lines.append(self._kv("Lat", f"{s.lat:+.4f}", w))
        lines.append(self._kv("Lon", f"{s.lon:+.4f}", w))
        lines.append(self._kv("Zoom", f"{s.z}", w, hot="0–9"))
        lines.append(self._kv("Heading", f"{s.heading_deg:5.1f}°", w))
        return lines

    def _build_search_lines(self, w: int) -> List:
        lines = []
        lines.append(self._section("Search", w))
        lines.append([("class:sidebar.label", " Goto: ")])
        # Input box
        focus_cls = "class:sidebar.input.focus" if self.search_focused else "class:sidebar.input"
        text = self.search_text or " "
        # Pad to width-2 so the field looks like a box.
        field_w = max(8, w - 2)
        line_text = (text + " " * field_w)[: field_w]
        lines.append([
            ("class:sidebar.value", " "),
            (focus_cls, line_text),
            ("class:sidebar.value", " "),
        ])
        lines.append([("class:sidebar.dim", " (Enter to go, Esc cancel)".ljust(w))])
        lines.append(self._spacer(w))
        lines.append(self._section("Examples", w))
        for ex in (
            "42.36, -71.06",
            "Boston",
            "53.3498, -6.2603",
        ):
            lines.append([("class:sidebar.dim", "  " + ex.ljust(w - 2))])
        return lines

    def _build_controls_lines(self, w: int) -> List:
        lines = []
        lines.append(self._section("Navigation", w))
        for key, desc in (
            ("↑↓←→", "pan"),
            ("Shift+↑↓←→", "pan ×4"),
            ("+ -", "zoom"),
            ("0-9", "jump zoom"),
            ("g", "goto…"),
            ("r", "home"),
            ("click", "recentre"),
            ("drag", "pan"),
            ("wheel", "zoom"),
        ):
            lines.append(self._kv(key, desc, w))
        lines.append(self._spacer(w))
        lines.append(self._section("Display", w))
        for key, desc in (
            ("v", "vector/raster"),
            ("k", "next source"),
            ("m", "mode"),
            ("t", "theme"),
            ("p", "palette"),
            ("d", "dither"),
            ("s", "shaded"),
            ("c", "color"),
            ("u", "threshold"),
        ):
            lines.append(self._kv(key, desc, w))
        lines.append(self._spacer(w))
        lines.append(self._section("Image", w))
        for key, desc in (
            ("[ / ]", "brightness ±"),
            ("{ / }", "contrast ±"),
            ("\\", "reset"),
        ):
            lines.append(self._kv(key, desc, w))
        lines.append(self._spacer(w))
        lines.append(self._section("App", w))
        for key, desc in (
            ("Tab", "toggle sidebar"),
            ("1-4", "switch tab"),
            ("h / ?", "help"),
            ("q", "quit"),
        ):
            lines.append(self._kv(key, desc, w))
        return lines

    def _build_integration_lines(self, w: int) -> List:
        lines: List = []
        traffic = self.get_traffic()
        registry = self.get_registry()

        lines.append(self._section("LandShark Link", w))
        if traffic is None:
            lines.append([("class:sidebar.dim", " not configured".ljust(w))])
            return lines

        st = traffic.status()
        ok_cls = "class:sidebar.ok" if st.connected else "class:sidebar.warn"
        lines.append([
            ("class:sidebar.label", " Status   "),
            (ok_cls, ("CONNECTED" if st.connected else "OFFLINE").ljust(w - 11)),
        ])
        lines.append(self._kv("Source", st.name, w))
        lines.append(self._kv("Target", st.detail or "-", w))
        # Last message age
        age = st.age_s()
        if age is None:
            age_text = "never"
        elif age < 1.0:
            age_text = "now"
        elif age < 60.0:
            age_text = f"{age:.0f}s ago"
        else:
            age_text = f"{age / 60:.1f}m ago"
        lines.append(self._kv("Last msg", age_text, w))
        lines.append(self._kv("Msgs/s", f"{st.msgs_per_sec:5.1f}", w))
        lines.append(self._kv("Bytes/s", _human_bytes(st.bytes_per_sec), w))
        if st.crc_good or st.crc_errors:
            ratio = st.crc_good / max(1, st.crc_good + st.crc_errors)
            lines.append(self._kv("CRC OK", f"{ratio*100:.1f}%", w))
        if st.signal_mag is not None:
            lines.append(self._kv("Signal", f"{st.signal_mag:.2f}", w))

        lines.append(self._spacer(w))
        lines.append(self._section(f"Aircraft ({len(registry) if registry else 0})", w))

        if registry is None:
            lines.append([("class:sidebar.dim", " no registry".ljust(w))])
            return lines

        ac_list = registry.snapshot()
        # Sort: with-position first, then by callsign / icao.
        ac_list.sort(key=lambda a: (not a.has_position(),
                                    (a.callsign or a.icao).strip()))
        if not ac_list:
            lines.append([("class:sidebar.dim", " (none yet)".ljust(w))])
        else:
            visible = ac_list[self.aircraft_scroll: self.aircraft_scroll + 8]
            for ac in visible:
                self._append_aircraft_row(lines, ac, w)

        # Selected-aircraft details panel
        sel = self.state.selected_aircraft_icao
        if sel and registry is not None:
            ac = registry.get(sel)
            if ac is not None:
                lines.append(self._spacer(w))
                lines.append(self._section(f"Selected: {ac.display_label()}", w))
                lines.append(self._kv("ICAO", ac.icao, w))
                if ac.callsign:
                    lines.append(self._kv("Callsign", ac.callsign, w))
                if ac.lat is not None and ac.lon is not None:
                    lines.append(self._kv("Lat", f"{ac.lat:+.4f}", w))
                    lines.append(self._kv("Lon", f"{ac.lon:+.4f}", w))
                if ac.altitude_ft is not None:
                    lines.append(self._kv("Altitude", f"{ac.altitude_ft:,.0f} ft", w))
                if ac.ground_speed_kt is not None:
                    lines.append(self._kv("Speed", f"{ac.ground_speed_kt:.0f} kt", w))
                if ac.track_deg is not None:
                    lines.append(self._kv("Track", f"{ac.track_deg:.0f}°", w))
                if ac.vertical_rate_fpm is not None:
                    arrow = "↑" if ac.vertical_rate_fpm > 50 else "↓" if ac.vertical_rate_fpm < -50 else "→"
                    lines.append(self._kv("VS", f"{arrow} {ac.vertical_rate_fpm:+.0f} fpm", w))
                if ac.squawk:
                    lines.append(self._kv("Squawk", ac.squawk, w))
                if ac.emergency:
                    lines.append([
                        ("class:sidebar.warn", " EMERGENCY".ljust(w))
                    ])
                lines.append(self._kv("Msgs", str(ac.msg_count), w))

        return lines

    def _append_aircraft_row(self, lines: List, ac: Aircraft, w: int) -> None:
        is_selected = (self.state.selected_aircraft_icao
                       and ac.icao == self.state.selected_aircraft_icao.upper())
        cls = "class:sidebar.aircraft.selected" if is_selected else "class:sidebar.aircraft"
        label = (ac.callsign or ac.icao)[:8].ljust(8)
        if ac.altitude_ft is not None:
            alt_text = f"{int(ac.altitude_ft / 100):>3}"   # FL
        else:
            alt_text = " --"
        if ac.ground_speed_kt is not None:
            sp_text = f"{int(ac.ground_speed_kt):>3}"
        else:
            sp_text = " --"
        marker = "▲" if ac.has_position() else "·"
        if ac.emergency:
            marker = "!"
        text = f" {marker} {label} FL{alt_text} {sp_text}kt"
        text = text[:w].ljust(w)
        # Record hit row at the (about-to-be-rendered) line index.
        y = len(lines)
        action = (lambda icao=ac.icao: self._on_aircraft_click(icao))
        self._hits.append((y, 0, len(text), action))
        lines.append([(cls, text)])

    def _on_aircraft_click(self, icao: str) -> None:
        # Toggle: clicking the selected aircraft deselects.
        cur = self.state.selected_aircraft_icao
        new = None if (cur and cur.upper() == icao.upper()) else icao.upper()
        self.on_select_aircraft(new)

    # ------------------------------------------------------------------
    # Frame composition
    # ------------------------------------------------------------------

    def create_content(self, width: int, height: int) -> UIContent:
        width = max(10, int(width))
        height = max(1, int(height))
        self._hits = []
        rows: List = []

        # Header
        title = " ◤ CartoTUI "
        rows.append([("class:sidebar.title", title.ljust(width))])

        # Tab strip — clickable
        rows.append(self._tab_strip(width))

        # Subtle separator
        rows.append([("class:sidebar.dim", "─" * width)])

        # Body
        tab = self.state.sidebar_tab
        if tab == TAB_SETTINGS:
            body = self._build_settings_lines(width)
        elif tab == TAB_SEARCH:
            body = self._build_search_lines(width)
        elif tab == TAB_CONTROLS:
            body = self._build_controls_lines(width)
        else:
            body = self._build_integration_lines(width)

        # Adjust hit y-coords: body rows are offset by len(rows)
        offset = len(rows)
        self._hits = [(y + offset, x0, x1, fn) for (y, x0, x1, fn) in self._hits]

        rows.extend(body)

        # Pad to height with blank sidebar-styled lines.
        while len(rows) < height:
            rows.append([("class:sidebar", " " * width)])

        # Trim if longer than height (don't drop the header).
        if len(rows) > height:
            rows = rows[:height]

        formatted = [to_formatted_text(r) for r in rows]
        return UIContent(
            get_line=lambda i: formatted[i] if 0 <= i < len(formatted)
                                else to_formatted_text([("class:sidebar", " " * width)]),
            line_count=len(formatted),
        )

    def _tab_strip(self, width: int) -> List:
        runs = []
        cursor = 0
        for i, name in enumerate(SIDEBAR_TABS):
            label = f" {i+1} {name} "
            cls = "class:sidebar.tab.active" if i == self.state.sidebar_tab else "class:sidebar.tab"
            x0 = cursor
            runs.append((cls, label))
            cursor += len(label)
            # Hit registers tab number
            self._hits.append((1, x0, cursor, (lambda idx=i: self.set_tab(idx))))
        # Pad
        if cursor < width:
            runs.append(("class:sidebar.tab", " " * (width - cursor)))
        elif cursor > width:
            # Truncate — this is purely cosmetic. In practice with sidebar
            # width >= 28 the four tabs fit fine.
            pass
        return runs

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mouse_handler(self, ev: MouseEvent):
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        x, y = ev.position.x, ev.position.y
        for (hy, x0, x1, fn) in self._hits:
            if hy == y and x0 <= x < x1:
                fn()
                return None
        # Clicking elsewhere on the sidebar — focus the search box if we're on
        # the Search tab.
        if self.state.sidebar_tab == TAB_SEARCH:
            self.search_focused = True
        return None

    # ------------------------------------------------------------------
    # Text input handling for search box
    # ------------------------------------------------------------------

    def search_keystroke(self, char: str) -> None:
        """Append a single character to the search text. Caller filters
        printable chars."""
        self.search_text += char

    def search_backspace(self) -> None:
        self.search_text = self.search_text[:-1]

    def search_clear(self) -> None:
        self.search_text = ""

    def search_submit(self) -> None:
        text = self.search_text.strip()
        if text:
            self.on_search_submit(text)
            self.search_text = ""

    # ------------------------------------------------------------------
    # Layout-assist helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _section(title: str, w: int) -> List:
        text = f" ── {title} ".ljust(w, "─")[:w]
        return [("class:sidebar.section", text)]

    @staticmethod
    def _kv(label: str, value: str, w: int, hot: Optional[str] = None) -> List:
        # One left-aligned label, one right-aligned value, optional hotkey
        # hint at the very end.
        label_w = max(8, w // 3)
        value_w = w - label_w - 1
        if hot:
            value_w -= len(hot) + 1
        if value_w < 4:
            value_w = 4
        lab = (" " + label).ljust(label_w)[:label_w]
        val = str(value)
        if len(val) > value_w:
            val = val[: value_w - 1] + "…"
        val = val.rjust(value_w)
        runs: List = [
            ("class:sidebar.label", lab),
            ("class:sidebar.value", " " + val),
        ]
        if hot:
            runs.append(("class:sidebar.hotkey", " " + hot))
        # Pad final width
        consumed = sum(len(t) for _, t in runs)
        if consumed < w:
            runs.append(("class:sidebar", " " * (w - consumed)))
        return runs

    @staticmethod
    def _spacer(w: int) -> List:
        return [("class:sidebar", " " * w)]


def _human_bytes(n: float) -> str:
    if n < 1024:
        return f"{n:.0f} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} kB"
    return f"{n/1024/1024:.2f} MB"


# ---------------------------------------------------------------------------
# Container façade — what app.py uses
# ---------------------------------------------------------------------------


class Sidebar:
    """Wrapper that gives the sidebar a ``__pt_container__`` and a width
    that respects ``MapState.sidebar_visible``."""

    def __init__(
        self,
        state: MapState,
        cfg: Config,
        get_traffic: Callable[[], Optional[TrafficSource]],
        get_registry: Callable[[], Optional[AircraftRegistry]],
        on_select_aircraft: Callable[[Optional[str]], None],
        on_search_submit: Callable[[str], None],
        width_chars: int = 36,
    ) -> None:
        self.state = state
        self.cfg = cfg
        self.width_chars = max(28, int(width_chars))
        self.control = SidebarControl(
            state, cfg, get_traffic, get_registry,
            on_select_aircraft, on_search_submit,
            width_chars=self.width_chars,
        )
        self.window = Window(
            content=self.control,
            width=self.width_chars,
            style="class:sidebar",
        )
        self.container = ConditionalContainer(
            content=self.window,
            filter=Condition(lambda: state.sidebar_visible),
        )

    def __pt_container__(self):
        return self.container

    # ------------------------------------------------------------------
    # Keybindings — registered when the sidebar takes focus.
    # ------------------------------------------------------------------

    def keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # Tab cycling on the sidebar itself
        @kb.add("c-right")
        def _(event):
            self.control.cycle_tab(+1)

        @kb.add("c-left")
        def _(event):
            self.control.cycle_tab(-1)

        for i in range(len(SIDEBAR_TABS)):
            @kb.add(str(i + 1))
            def _(event, idx=i):
                self.control.set_tab(idx)

        # Search input
        @kb.add("enter")
        def _(event):
            if self.state.sidebar_tab == TAB_SEARCH:
                self.control.search_submit()

        @kb.add("backspace")
        def _(event):
            if self.state.sidebar_tab == TAB_SEARCH:
                self.control.search_backspace()

        @kb.add("escape")
        def _(event):
            if self.state.sidebar_tab == TAB_SEARCH:
                self.control.search_clear()

        # Aircraft list scrolling on Integration
        @kb.add("up")
        def _(event):
            if self.state.sidebar_tab == TAB_INTEGRATION:
                self.control.aircraft_scroll = max(0, self.control.aircraft_scroll - 1)

        @kb.add("down")
        def _(event):
            if self.state.sidebar_tab == TAB_INTEGRATION:
                self.control.aircraft_scroll += 1

        # Printable input — only consume when on Search tab so other tabs'
        # keys (t, p, m, etc.) still pass through to the global app.
        @kb.add("<any>")
        def _(event):
            if self.state.sidebar_tab != TAB_SEARCH:
                return
            data = event.data
            if not data or not data.isprintable():
                return
            self.control.search_keystroke(data)

        return kb
