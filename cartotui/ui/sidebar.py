
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui.config import Config
from cartotui.themes import (
    border_chars,
    group_box_bottom,
    tab_strip_rows,
    tab_strip_slot_ranges,
)
from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.interest import classify
from cartotui.traffic.source import TrafficSource
from cartotui.ui.state import MapState

def _distance_bearing_nm(lat1: float, lon1: float,
                         lat2: float, lon2: float) -> Tuple[float, float]:
    import math
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    dist = 2 * r_nm * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dlmb) * math.cos(p2)
    x = (math.cos(p1) * math.sin(p2)
         - math.sin(p1) * math.cos(p2) * math.cos(dlmb))
    brg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return dist, brg

def _compass_point(bearing: float) -> str:
    dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return dirs[int((bearing + 22.5) % 360 / 45)]

SIDEBAR_TABS: Tuple[str, ...] = ("Settings", "Search", "Controls", "Integration", "Performance")
_TAB_ABBREV: Tuple[str, ...] = ("Set", "Sch", "Ctl", "Int", "Prf")

TAB_SETTINGS    = 0
TAB_SEARCH      = 1
TAB_CONTROLS    = 2
TAB_INTEGRATION = 3
TAB_PERFORMANCE = 4

def _get_bc(cfg: Config) -> dict:
    theme = cfg["ui"].get("theme", "amber")
    style = cfg["ui"].get("border_style", "heavy")
    return border_chars(style, theme)

class SidebarControl(UIControl):

    def __init__(
        self,
        state: MapState,
        cfg: Config,
        get_traffic: Callable[[], Optional[TrafficSource]],
        get_registry: Callable[[], Optional[AircraftRegistry]],
        on_select_aircraft: Callable[[Optional[str]], None],
        on_search_submit: Callable[[str], None],
        width_chars: int,
        on_perf_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state = state
        self.cfg = cfg
        self.get_traffic = get_traffic
        self.get_registry = get_registry
        self.on_select_aircraft = on_select_aircraft
        self.on_search_submit = on_search_submit
        self.on_perf_changed = on_perf_changed
        self.width_chars = max(28, int(width_chars))
        self._hits: List[Tuple[int, int, int, Callable[[], None]]] = []
        self.search_text: str = ""
        self.search_focused: bool = False
        self.aircraft_scroll: int = 0
        self.collapsed: bool = False
        self.on_hide: Optional[Callable[[], None]] = None

    def is_focusable(self) -> bool:
        return True

    def preferred_width(self, max_available_width: int) -> int:
        return min(self.width_chars, max_available_width)

    def _toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        from prompt_toolkit.application.current import get_app_or_none
        app = get_app_or_none()
        if app:
            app.invalidate()

    def _hide(self) -> None:
        if self.on_hide is not None:
            self.on_hide()
        else:
            self.state.sidebar_visible = False

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        if self.collapsed:
            return min(1, max_available_height)
        bc = _get_bc(self.cfg)
        saved = self._hits
        self._hits = []
        try:
            body = self._body_for_tab(max(10, int(width)), bc)
        finally:
            self._hits = saved
        return min(3 + len(body), max_available_height)

    def _body_for_tab(self, width: int, bc: dict) -> List:
        tab = self.state.sidebar_tab
        if tab == TAB_SETTINGS:
            return self._build_settings_lines(width, bc)
        if tab == TAB_SEARCH:
            return self._build_search_lines(width, bc)
        if tab == TAB_CONTROLS:
            return self._build_controls_lines(width, bc)
        if tab == TAB_INTEGRATION:
            return self._build_integration_lines(width, bc)
        return self._build_performance_lines(width, bc)

    def set_tab(self, idx: int) -> None:
        idx = max(0, min(len(SIDEBAR_TABS) - 1, int(idx)))
        self.state.sidebar_tab = idx
        self.aircraft_scroll = 0

    def cycle_tab(self, delta: int) -> None:
        self.set_tab((self.state.sidebar_tab + delta) % len(SIDEBAR_TABS))

    def _build_settings_lines(self, w: int, bc: dict) -> List:
        from cartotui import looks
        s = self.state
        lines = []

        active = looks.current_look_key(s, self.cfg)
        look_name = looks.get_look(active).name if active else "Custom"
        lines.append(self._section("Look", w, bc))
        lines.append(self._kv("Style", look_name, w, bc, hot="l"))
        lines.append([("class:sidebar.dim",
                       (bc["v"] + "  l = next   L = gallery").ljust(w - 1)
                       + bc["v"])])
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Fine-tune", w, bc))
        lines.append(self._kv("Theme",   s.theme,                           w, bc, hot="t"))
        lines.append(self._kv("Palette", s.palette,                         w, bc, hot="p"))
        lines.append(self._kv("Render",  s.render_mode,                     w, bc, hot="m"))
        lines.append(self._kv("Source",  s.source,                          w, bc, hot="v"))
        lines.append(self._kv("Color",   "on" if s.color else "off",        w, bc, hot="c"))
        lines.append(self._kv("Dither",  s.dither,                          w, bc, hot="d"))
        lines.append(self._kv("Shaded",  "on" if s.shaded_blocks else "off",w, bc, hot="s"))
        lines.append(self._kv("Labels",  "on" if s.labels else "off",       w, bc, hot="N"))
        lines.append(self._kv("Threshold",  s.threshold_mode,          w, bc, hot="u"))
        lines.append(self._kv("Brightness", f"{s.brightness:+.2f}",   w, bc, hot="[/]"))
        lines.append(self._kv("Contrast",   f"{s.contrast:+.2f}",     w, bc, hot="{/}"))
        lines.append(self._kv("Gamma",      f"{s.gamma:+.2f}",        w, bc, hot="(/)"))
        lines.append(self._kv("Saturation", f"{s.saturation:+.2f}",   w, bc, hot="</>"))
        lines.append(self._kv("Black pt",   f"{s.black_point:.2f}",   w, bc, hot=";/:"))
        lines.append(self._kv("White pt",   f"{s.white_point:.2f}",   w, bc, hot="'/\""))
        lines.append(self._section_end(w, bc))

        lines.append(self._section("View", w, bc))
        lines.append(self._kv("Lat",     f"{s.lat:+.4f}",         w, bc))
        lines.append(self._kv("Lon",     f"{s.lon:+.4f}",         w, bc))
        lines.append(self._kv("Zoom",    f"z{s.z}",               w, bc, hot="0-9"))
        lines.append(self._kv("Heading", f"{s.heading_deg:5.1f}°",w, bc))
        lines.append(self._section_end(w, bc))
        return lines

    def _perf_row(self, lines: List, label: str, value: str, w: int, bc: dict,
                  action: Optional[Callable[[], None]] = None) -> None:
        v = bc["v"]
        vlen = len(v)
        hint = " ▸" if action is not None else "  "
        ls = " " + label
        value = str(value)
        content = w - 2 * vlen
        gap = content - len(ls) - len(value) - len(hint)
        if gap < 1:
            maxval = content - len(ls) - len(hint) - 1
            value = value[:max(0, maxval)]
            gap = max(0, content - len(ls) - len(value) - len(hint))
        y = len(lines)
        if action is not None:
            self._hits.append((y, 0, w, action))
        lines.append([
            ("class:sidebar.dim", v),
            ("class:sidebar.label", ls),
            ("class:sidebar", " " * gap),
            ("class:sidebar.value", value),
            ("class:sidebar.hotkey" if action is not None else "class:sidebar.dim", hint),
            ("class:sidebar.dim", v),
        ])

    def _perf_apply(self, patch: dict, rerender: bool = True) -> None:
        self.cfg.update(patch)
        try:
            self.cfg.save()
        except Exception:
            pass
        if rerender and self.on_perf_changed is not None:
            self.on_perf_changed()
        else:
            from prompt_toolkit.application.current import get_app_or_none
            app = get_app_or_none()
            if app:
                app.invalidate()

    def _build_performance_lines(self, w: int, bc: dict) -> List:
        r = self.cfg["render"]
        m = self.cfg["map"]
        pf = self.cfg["prefetch"]
        at = self.cfg["aircraft_trails"]
        ui = self.cfg["ui"]
        ca = self.cfg["cache"]
        lines: List = []

        lines.append(self._section("Renderer", w, bc))
        self._perf_row(lines, "Engine", r.get("vector_engine", "libcarto"),
                       w, bc, self._perf_toggle_engine)
        scale = int(r.get("vector_scale", 6))
        qual = {2: "fastest", 3: "fast", 4: "balanced",
                6: "sharp", 8: "max"}.get(scale, str(scale))
        self._perf_row(lines, "Quality", qual, w, bc, self._perf_cycle_quality)
        self._perf_row(lines, "Overzoom", str(int(m.get("overzoom", 2))),
                       w, bc, self._perf_cycle_overzoom)
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Tiles", w, bc))
        self._perf_row(lines, "Prefetch", "on" if pf.get("enable", True) else "off",
                       w, bc, self._perf_toggle_prefetch)
        cache_mb = int(int(ca.get("max_bytes", 268435456)) // (1024 * 1024))
        self._perf_row(lines, "Cache", f"{cache_mb} MB", w, bc, self._perf_cycle_cache)
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Display", w, bc))
        self._perf_row(lines, "Trails", "on" if at.get("enabled", True) else "off",
                       w, bc, self._perf_toggle_trails)
        self._perf_row(lines, "Latency", "on" if ui.get("show_latency", True) else "off",
                       w, bc, self._perf_toggle_latency)
        self._perf_row(lines, "Render", f"{self.state.last_render_ms:.0f} ms", w, bc)
        lines.append(self._section_end(w, bc))
        return lines

    def _perf_toggle_engine(self) -> None:
        cur = self.cfg["render"].get("vector_engine", "libcarto")
        self._perf_apply({"render": {"vector_engine":
                          "python" if cur == "libcarto" else "libcarto"}})

    def _perf_cycle_quality(self) -> None:
        order = [3, 4, 6, 8]
        cur = int(self.cfg["render"].get("vector_scale", 6))
        idx = order.index(cur) if cur in order else 2
        self._perf_apply({"render": {"vector_scale": order[(idx + 1) % len(order)]}})

    def _perf_cycle_overzoom(self) -> None:
        cur = int(self.cfg["map"].get("overzoom", 2))
        self._perf_apply({"map": {"overzoom": (cur + 1) % 5}})

    def _perf_toggle_prefetch(self) -> None:
        cur = bool(self.cfg["prefetch"].get("enable", True))
        self._perf_apply({"prefetch": {"enable": not cur}}, rerender=False)

    def _perf_cycle_cache(self) -> None:
        order = [128, 256, 512, 1024]
        cur = int(int(self.cfg["cache"].get("max_bytes", 268435456)) // (1024 * 1024))
        idx = order.index(cur) if cur in order else 1
        self._perf_apply(
            {"cache": {"max_bytes": order[(idx + 1) % len(order)] * 1024 * 1024}},
            rerender=False)

    def _perf_toggle_trails(self) -> None:
        cur = bool(self.cfg["aircraft_trails"].get("enabled", True))
        self._perf_apply({"aircraft_trails": {"enabled": not cur}})

    def _perf_toggle_latency(self) -> None:
        cur = bool(self.cfg["ui"].get("show_latency", True))
        self._perf_apply({"ui": {"show_latency": not cur}}, rerender=False)

    def _build_search_lines(self, w: int, bc: dict) -> List:
        v = bc["v"]
        lines = []
        lines.append(self._section("Search", w, bc))
        lines.append([("class:sidebar.label", v + " Goto:"),
                      ("class:sidebar",       " " * max(0, w - len(v + " Goto:") - 1) + v)])
        focus_cls = "class:sidebar.input.focus" if self.search_focused else "class:sidebar.input"
        field_w = max(4, w - 4)
        text = (self.search_text or " ")
        field_text = (text + " " * field_w)[:field_w]
        lines.append([
            ("class:sidebar", v + " "),
            (focus_cls, field_text),
            ("class:sidebar", " " + v),
        ])
        hint = "(Enter to go, Esc to clear)"
        lines.append([("class:sidebar.dim", v + " " + hint.ljust(w - 3) + " " + v)])
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Examples", w, bc))
        for ex in (
            "43.2081, -71.5376",
            "Concord NH",
            "44.2706, -71.3033",
        ):
            row = v + " " + ex
            lines.append([("class:sidebar.dim", (row + " " * w)[:w - 1] + v)])
        lines.append(self._section_end(w, bc))
        return lines

    def _build_controls_lines(self, w: int, bc: dict) -> List:
        lines = []
        lines.append(self._section("Navigation", w, bc))
        for key, desc in (
            ("↑↓←→",       "pan"),
            ("Shift+↑↓←→", "pan ×4"),
            ("+ -",         "zoom"),
            ("0-9",         "jump zoom"),
            ("g",           "goto…"),
            ("r",           "home"),
            ("click",       "recentre"),
            ("drag",        "pan"),
            ("wheel",       "zoom"),
        ):
            lines.append(self._kv(key, desc, w, bc))
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Looks", w, bc))
        for key, desc in (
            ("l", "next look"),
            ("L", "looks gallery"),
        ):
            lines.append(self._kv(key, desc, w, bc))
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Fine-tune", w, bc))
        for key, desc in (
            ("v", "vector/raster"),
            ("k", "next source"),
            ("m", "mode"),
            ("t", "theme"),
            ("p", "palette"),
            ("d", "dither"),
            ("s", "shaded"),
            ("c", "color"),
            ("N", "map labels"),
            ("u", "threshold"),
        ):
            lines.append(self._kv(key, desc, w, bc))
        lines.append(self._section_end(w, bc))

        lines.append(self._section("Image", w, bc))
        for key, desc in (
            ("[ / ]", "brightness ±"),
            ("{ / }", "contrast ±"),
            ("( / )", "gamma ±"),
            ("< / >", "saturation ±"),
            ("; / :", "black point ± (lift darks)"),
            ("' / \"", "white point ± (tame brights)"),
            ("\\",    "reset"),
        ):
            lines.append(self._kv(key, desc, w, bc))
        lines.append(self._section_end(w, bc))

        lines.append(self._section("App", w, bc))
        for key, desc in (
            ("Tab",  "toggle sidebar"),
            ("w",    "widgets"),
            ("1-4",  "switch tab"),
            ("h / ?","help"),
            ("q",    "quit"),
        ):
            lines.append(self._kv(key, desc, w, bc))
        lines.append(self._section_end(w, bc))
        return lines

    def _build_integration_lines(self, w: int, bc: dict) -> List:
        lines: List = []
        traffic = self.get_traffic()
        registry = self.get_registry()
        v = bc["v"]

        _link_titles = {
            "api": "ADS-B API Link", "sbs1": "SBS-1 Link",
            "lakeshark": "LakeShark Link", "disabled": "Traffic Link",
        }
        link_title = "Traffic Link"
        if traffic is not None:
            link_title = _link_titles.get(traffic.status().name, "Traffic Link")
        lines.append(self._section(link_title, w, bc))
        if traffic is None:
            lines.append([("class:sidebar.dim", (v + " not configured").ljust(w - 1) + v)])
            lines.append(self._section_end(w, bc))
            return lines

        st = traffic.status()
        ok_cls = "class:sidebar.ok" if st.connected else "class:sidebar.warn"
        conn_text = "CONNECTED" if st.connected else "OFFLINE"
        row = v + " Status:  "
        pad = w - len(row) - len(conn_text) - 2
        lines.append([
            ("class:sidebar.label", row),
            (ok_cls, conn_text + " " * max(0, pad)),
            ("class:sidebar", " " + v),
        ])
        lines.append(self._kv("Source", st.name, w, bc))
        lines.append(self._kv("Target", st.detail or "-", w, bc))

        age = st.age_s()
        if age is None:
            age_text = "never"
        elif age < 1.0:
            age_text = "now"
        elif age < 60.0:
            age_text = f"{age:.0f}s ago"
        else:
            age_text = f"{age / 60:.1f}m ago"
        lines.append(self._kv("Last msg", age_text, w, bc))
        lines.append(self._kv("Msgs/s",  f"{st.msgs_per_sec:5.1f}", w, bc))
        lines.append(self._kv("Bytes/s", _human_bytes(st.bytes_per_sec), w, bc))
        if st.crc_good or st.crc_errors:
            ratio = st.crc_good / max(1, st.crc_good + st.crc_errors)
            lines.append(self._kv("CRC OK", f"{ratio*100:.1f}%", w, bc))
        if st.signal_mag is not None:
            lines.append(self._kv("Signal", f"{st.signal_mag:.2f}", w, bc))
        if st.parse_errors:
            lines.append(self._kv("Parse err", str(st.parse_errors), w, bc))

        if (st.bytes_per_sec > 100 and st.msgs_per_sec < 0.1
                and st.messages_total == 0):
            ls_cfg = self.cfg.get("traffic", {}).get("lakeshark", {})
            tx_pin = int(ls_cfg.get("tx_pin", 48))
            baud = int(ls_cfg.get("baudrate", 115200))
            lines.append([("class:sidebar.warn",
                           (v + " bytes flowing, no JSONL frames").ljust(w - 1) + v)])
            lines.append([("class:sidebar.dim",
                           (v + f" GPIO {tx_pin}, {baud} baud").ljust(w - 1) + v)])
        lines.append(self._section_end(w, bc))

        ac_count = len(registry) if registry else 0
        lines.append(self._section(f"Aircraft ({ac_count})", w, bc))

        if registry is None:
            lines.append([("class:sidebar.dim", (v + " no registry").ljust(w - 1) + v)])
            lines.append(self._section_end(w, bc))
            return lines

        clat, clon = self.state.lat, self.state.lon

        def _proximity(a):
            if not a.has_position():
                return (1, 0.0)
            return (0, (a.lat - clat) ** 2 + (a.lon - clon) ** 2)

        ac_list = registry.snapshot()
        ac_list.sort(key=_proximity)
        if not ac_list:
            lines.append([("class:sidebar.dim", (v + " (none yet)").ljust(w - 1) + v)])
        else:
            visible = ac_list[self.aircraft_scroll: self.aircraft_scroll + 8]
            for ac in visible:
                self._append_aircraft_row(lines, ac, w, v)

        sel = self.state.selected_aircraft_icao
        if sel and registry is not None:
            ac = registry.get(sel)
            if ac is not None:
                lines.append(self._section_end(w, bc))
                lines.append(self._section(f"Sel: {ac.display_label()}", w, bc))
                lines.append(self._kv("ICAO",     ac.icao, w, bc))
                if ac.callsign:
                    lines.append(self._kv("Callsign", ac.callsign, w, bc))
                if ac.registration:
                    lines.append(self._kv("Reg", ac.registration, w, bc))
                if ac.type_code or ac.type_desc:
                    tval = ac.type_code or ""
                    if ac.type_desc:
                        tval = (tval + " " + ac.type_desc).strip()
                    lines.append(self._kv("Type", tval, w, bc))
                if ac.operator:
                    lines.append(self._kv("Operator", ac.operator, w, bc))
                if ac.lat is not None and ac.lon is not None:
                    lines.append(self._kv("Lat", f"{ac.lat:+.4f}", w, bc))
                    lines.append(self._kv("Lon", f"{ac.lon:+.4f}", w, bc))
                    dist, brg = _distance_bearing_nm(
                        self.state.lat, self.state.lon, ac.lat, ac.lon)
                    lines.append(self._kv(
                        "Range", f"{dist:.1f} nm {_compass_point(brg)} {brg:.0f}°",
                        w, bc))
                if ac.altitude_ft is not None:
                    lines.append(self._kv("Altitude", f"{ac.altitude_ft:,.0f} ft", w, bc))
                if ac.ground_speed_kt is not None:
                    lines.append(self._kv("Speed", f"{ac.ground_speed_kt:.0f} kt", w, bc))
                if ac.track_deg is not None:
                    lines.append(self._kv("Track", f"{ac.track_deg:.0f}°", w, bc))
                if ac.vertical_rate_fpm is not None:
                    arrow = ("↑" if ac.vertical_rate_fpm > 50 else
                             "↓" if ac.vertical_rate_fpm < -50 else "→")
                    lines.append(self._kv("VS", f"{arrow} {ac.vertical_rate_fpm:+.0f} fpm", w, bc))
                if ac.squawk:
                    lines.append(self._kv("Squawk", ac.squawk, w, bc))
                interest = classify(ac)
                if interest:
                    tag_cls = ("class:sidebar.warn" if interest.is_alert
                               else "class:sidebar.dim")
                    tag_text = " " + " ".join(interest.tags)
                    lines.append([(tag_cls, tag_text.ljust(w - 1) + v)])
                lines.append(self._kv("Msgs", str(ac.msg_count), w, bc))
        lines.append(self._section_end(w, bc))
        return lines

    def _append_aircraft_row(self, lines: List, ac: Aircraft, w: int, v: str) -> None:
        is_selected = (self.state.selected_aircraft_icao
                       and ac.icao == self.state.selected_aircraft_icao.upper())
        cls = "class:sidebar.aircraft.selected" if is_selected else "class:sidebar.aircraft"
        label = (ac.callsign or ac.icao)[:8].ljust(8)
        alt_text = f"{int(ac.altitude_ft / 100):>3}" if ac.altitude_ft is not None else " --"
        sp_text  = f"{int(ac.ground_speed_kt):>3}" if ac.ground_speed_kt is not None else " --"
        marker = "▲" if ac.has_position() else "·"
        if ac.emergency:
            marker = "!"
        inner = f" {marker} {label} FL{alt_text} {sp_text}kt"
        inner_w = w - 2
        inner = (inner + " " * inner_w)[:inner_w]
        text = v + inner + v
        y = len(lines)
        action = (lambda icao=ac.icao: self._on_aircraft_click(icao))
        self._hits.append((y, 0, len(text), action))
        lines.append([(cls, text)])

    def _on_aircraft_click(self, icao: str) -> None:
        cur = self.state.selected_aircraft_icao
        new = None if (cur and cur.upper() == icao.upper()) else icao.upper()
        self.on_select_aircraft(new)

    def create_content(self, width: int, height: int) -> UIContent:
        width = max(10, int(width))
        height = max(1, int(height))
        self._hits = []
        rows: List = []

        bc = _get_bc(self.cfg)

        title_text = " Terminalbay.com"
        collapse = "[+]" if self.collapsed else "[-]"
        close = "[x]"
        btns = collapse + close
        avail = max(1, width - len(btns))
        rows.append([("class:sidebar.title", title_text.ljust(avail)[:avail]),
                     ("class:sidebar.hotkey", btns)])
        self._hits.append((0, avail, avail + len(collapse), self._toggle_collapse))
        self._hits.append((0, avail + len(collapse), avail + len(btns), self._hide))

        if self.collapsed:
            out_rows = rows[:]
            while len(out_rows) < height:
                out_rows.append([("class:sidebar", " " * width)])
            out_rows = out_rows[:height]
            formatted = [to_formatted_text(r) for r in out_rows]
            return UIContent(
                get_line=lambda i: formatted[i] if 0 <= i < len(formatted)
                                    else to_formatted_text([("class:sidebar", " " * width)]),
                line_count=len(formatted),
            )

        top_str, label_str = tab_strip_rows(_TAB_ABBREV, self.state.sidebar_tab, width, bc)
        rows.append([("class:sidebar.tab", top_str)])

        slot_ranges = tab_strip_slot_ranges(_TAB_ABBREV, width)
        label_runs = []
        for i, (s0, s1) in enumerate(slot_ranges):
            if i == 0:
                label_runs.append(("class:sidebar.tab", label_str[0:s0]))
            tab_cls = ("class:sidebar.tab.active"
                       if i == self.state.sidebar_tab else "class:sidebar.tab")
            slot_text = label_str[s0:s1]
            label_runs.append((tab_cls, slot_text))
            self._hits.append((2, s0, s1, (lambda idx=i: self.set_tab(idx))))
            if s1 < len(label_str):
                label_runs.append(("class:sidebar.tab", label_str[s1:s1 + 1]))

        last_s1 = slot_ranges[-1][1] + 1 if slot_ranges else 0
        if last_s1 < len(label_str):
            label_runs.append(("class:sidebar.tab", label_str[last_s1:]))

        rows.append(label_runs)

        pre_body = len(self._hits)
        body = self._body_for_tab(width, bc)

        offset = len(rows)
        self._hits = [
            h if i < pre_body else (h[0] + offset, h[1], h[2], h[3])
            for i, h in enumerate(self._hits)
        ]

        rows.extend(body)

        while len(rows) < height:
            rows.append([("class:sidebar", " " * width)])

        if len(rows) > height:
            rows = rows[:height]

        formatted = [to_formatted_text(r) for r in rows]
        return UIContent(
            get_line=lambda i: formatted[i] if 0 <= i < len(formatted)
                                else to_formatted_text([("class:sidebar", " " * width)]),
            line_count=len(formatted),
        )

    def mouse_handler(self, ev: MouseEvent):
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        x, y = ev.position.x, ev.position.y
        for (hy, x0, x1, fn) in self._hits:
            if hy == y and x0 <= x < x1:
                fn()
                return None
        if self.state.sidebar_tab == TAB_SEARCH:
            self.search_focused = True
        return None

    def search_keystroke(self, char: str) -> None:
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

    @staticmethod
    def _section(title: str, w: int, bc: dict) -> List:
        h = bc["h"]
        tl = bc["tl"]
        tr = bc["tr"]
        prefix = tl + h + " "
        pad = max(0, w - len(prefix) - len(title) - 2)
        suffix = " " + h * pad + tr
        return [
            ("class:sidebar.dim",     prefix),
            ("class:sidebar.section", title),
            ("class:sidebar.dim",     suffix),
        ]

    @staticmethod
    def _section_end(w: int, bc: dict) -> List:
        text = group_box_bottom(w, bc)
        return [("class:sidebar.dim", text)]

    @staticmethod
    def _kv(label: str, value: str, w: int, bc: dict,
            hot: Optional[str] = None) -> List:
        v = bc["v"]
        label_str = " " + label + ":"
        hot_str = f" [{hot}]" if hot else ""
        inner = w - 2
        val_w = inner - len(label_str) - len(hot_str) - 1
        if val_w < 1:
            val_w = 1
        val = str(value)
        if len(val) > val_w:
            val = val[:val_w - 1] + "…"
        val = val.rjust(val_w)
        runs: List = [
            ("class:sidebar.dim",    v),
            ("class:sidebar.label",  label_str),
            ("class:sidebar.value",  " " + val),
        ]
        if hot_str:
            runs.append(("class:sidebar.hotkey", hot_str))
        runs.append(("class:sidebar.value", " "))
        runs.append(("class:sidebar.dim", v))
        consumed = sum(len(t) for _, t in runs)
        if consumed < w:
            runs[-1] = ("class:sidebar.dim", v)
            runs.insert(-1, ("class:sidebar.value", " " * (w - consumed)))
        elif consumed > w:
            excess = consumed - w
            val = val[:-excess] if excess < len(val) else " "
            runs = [
                ("class:sidebar.dim",    v),
                ("class:sidebar.label",  label_str),
                ("class:sidebar.value",  " " + val),
            ]
            if hot_str:
                runs.append(("class:sidebar.hotkey", hot_str))
            runs.append(("class:sidebar.value", " "))
            runs.append(("class:sidebar.dim", v))
        return runs

def _human_bytes(n: float) -> str:
    if n < 1024:
        return f"{n:.0f} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} kB"
    return f"{n/1024/1024:.2f} MB"

class Sidebar:

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

    def keybindings(self) -> KeyBindings:
        kb = KeyBindings()

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

        @kb.add("up")
        def _(event):
            if self.state.sidebar_tab == TAB_INTEGRATION:
                self.control.aircraft_scroll = max(0, self.control.aircraft_scroll - 1)

        @kb.add("down")
        def _(event):
            if self.state.sidebar_tab == TAB_INTEGRATION:
                self.control.aircraft_scroll += 1

        @kb.add("<any>")
        def _(event):
            if self.state.sidebar_tab != TAB_SEARCH:
                return
            data = event.data
            if not data or not data.isprintable():
                return
            self.control.search_keystroke(data)

        return kb
