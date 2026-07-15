from __future__ import annotations

import math
from typing import Optional

from cartotui.aircraft_colors import altitude_color
from cartotui.traffic.interest import classify
from cartotui.traffic.silhouette import silhouette
from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_LABEL_MODES = ["smart", "all", "selected", "none"]
_MARKER_STYLES = ["arrow", "dot", "large", "plane", "square"]
_DENSITY_STEPS = [50, 150, 500, 0]
_TRACK_ZOOM = 12

_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

def _hexstyle(rgb, bold: bool = False) -> str:
    r, g, b = rgb
    return f"fg:#{r:02x}{g:02x}{b:02x}" + (" bold" if bold else "")

@register_widget
class AdsbWidget(Widget):
    name = "adsb"
    title = "ADS-B"
    default_width = 40
    default_top = 2
    default_left = 24
    default_visible = False

    def _ac(self) -> dict:
        data = getattr(self.ctx.cfg, "data", None)
        if not isinstance(data, dict):
            return {}
        ac = data.setdefault("aircraft", {})
        if not isinstance(ac, dict):
            ac = {}
            data["aircraft"] = ac
        return ac

    def _set(self, key: str, value) -> None:
        self._ac()[key] = value
        self.ctx.rerender()

    def _toggle(self, key: str, default: bool = True) -> None:
        self._set(key, not bool(self._ac().get(key, default)))

    def _cycle(self, key: str, options, default) -> None:
        cur = self._ac().get(key, default)
        i = options.index(cur) if cur in options else 0
        self._set(key, options[(i + 1) % len(options)])

    def _toggle_trails(self) -> None:
        data = self.ctx.cfg.data
        t = data.setdefault("aircraft_trails", {})
        t["enabled"] = not bool(t.get("enabled", True))
        self.ctx.rerender()

    def build(self, width: int) -> None:
        ac = self._ac()
        registry = self.ctx.aircraft_registry
        st = self.ctx.state
        sel_icao = getattr(st, "selected_aircraft_icao", None)

        self._build_link(width, registry)
        self._build_selected(width, registry, sel_icao)
        self._build_display(width, ac)
        self._build_density(width, ac)
        self._build_list(width, registry, sel_icao)

    def _build_link(self, width: int, registry) -> None:
        get_traffic = self.ctx.get_traffic
        traffic = get_traffic() if get_traffic else None
        count = len(registry) if registry else 0
        self.add_section(f"Link · {count} aircraft", width)
        if traffic is None:
            self.add_dim("not configured", width)
            return
        stt = traffic.status()
        state = "● CONNECTED" if stt.connected else "○ OFFLINE"
        self.add_kv("Status", state, width)
        self.add_kv("Source", f"{stt.name}  {stt.msgs_per_sec:.0f}/s", width)

    def _build_selected(self, width, registry, sel_icao) -> None:
        ac = registry.get(sel_icao) if (registry and sel_icao) else None
        if ac is None:
            self.add_section("Selected", width)
            self.add_dim("click a plane on the map", width)
            return

        self.add_section(f"Selected · {ac.display_label()}", width)

        color = altitude_color(ac.altitude_ft, bool(ac.on_ground))
        for row in silhouette(ac.category, ac.type_code):
            pad = max(0, (width - len(row)) // 2)
            self.add_row([("class:panel", " " * pad),
                          (_hexstyle(color, bold=True), row)], width)

        if ac.type_desc or ac.type_code:
            self.add_kv("Type", (ac.type_desc or ac.type_code)[:width - 8], width)
        if ac.operator:
            self.add_kv("Operator", ac.operator[:width - 12], width)
        if ac.registration:
            self.add_kv("Reg", ac.registration, width)
        if ac.altitude_ft is not None:
            vs = ""
            if ac.vertical_rate_fpm:
                vs = " ↑" if ac.vertical_rate_fpm > 50 else (
                    " ↓" if ac.vertical_rate_fpm < -50 else "")
            self.add_kv("Alt", f"{ac.altitude_ft:,.0f} ft{vs}", width)
        if ac.ground_speed_kt is not None:
            self.add_kv("Speed", f"{ac.ground_speed_kt:.0f} kt", width)
        rng = self._range_to(ac)
        if rng:
            self.add_kv("Range", rng, width)
        it = classify(ac)
        if it:
            style = "class:panel.warn" if it.is_alert else "class:panel.dim"
            self.add_row([(style, self._pad(" " + " ".join(it.tags), width))],
                         width)

        follow_on = bool(self._ac().get("follow_selected", False))
        self.add_kv("Follow", "ON" if follow_on else "off", width,
                    action=self._toggle_follow)
        self.add_button("Follow + zoom", width, self._follow_zoom)
        self.add_button("Center here", width, lambda: self._center_on(ac))
        self.add_button("Deselect", width, self._deselect)

    def _build_display(self, width, ac) -> None:
        self.add_section("Display", width)
        self.add_kv("Labels", str(ac.get("label_mode", "smart")), width,
                    action=lambda: self._cycle("label_mode", _LABEL_MODES, "smart"))
        self.add_kv("Markers", str(ac.get("marker_style", "arrow")), width,
                    action=lambda: self._cycle("marker_style", _MARKER_STYLES, "arrow"))
        self.add_kv("Alt colours", _on(ac.get("altitude_colors", True)), width,
                    action=lambda: self._toggle("altitude_colors"))
        self.add_kv("Legend", _on(ac.get("legend", True)), width,
                    action=lambda: self._toggle("legend"))
        trails = self.ctx.cfg.data.get("aircraft_trails", {})
        self.add_kv("Trails", _on(trails.get("enabled", True)), width,
                    action=self._toggle_trails)
        self.add_kv("Predicted", _on(ac.get("predict_track", True)), width,
                    action=lambda: self._toggle("predict_track"))
        self.add_kv("Motion (DR)", _on(ac.get("dead_reckoning", True)), width,
                    action=lambda: self._toggle("dead_reckoning"))
        self.add_kv("Highlight", _on(ac.get("highlight_interesting", True)), width,
                    action=lambda: self._toggle("highlight_interesting"))

    def _build_density(self, width, ac) -> None:
        self.add_section("Declutter", width)
        mx = int(ac.get("max_shown", 150) or 0)
        self.add_kv("Max shown", "all" if mx == 0 else str(mx), width,
                    action=lambda: self._cycle("max_shown", _DENSITY_STEPS, 150))
        self.add_kv("Ground", "hidden" if ac.get("hide_ground") else "shown", width,
                    action=lambda: self._toggle("hide_ground", default=False))

    def _build_list(self, width, registry, sel_icao) -> None:
        if not registry or len(registry) == 0:
            return
        st = self.ctx.state
        clat, clon = st.lat, st.lon

        def prox(a):
            if not a.has_position():
                return (1, 0.0)
            return (0, (a.lat - clat) ** 2 + (a.lon - clon) ** 2)

        ac_list = sorted(registry.snapshot(), key=prox)
        self.add_section("Nearest", width)
        for ac in ac_list[:6]:
            label = (ac.callsign or ac.icao)[:8].ljust(8)
            alt = f"{int(ac.altitude_ft / 100):>3}" if ac.altitude_ft is not None else " --"
            spd = f"{int(ac.ground_speed_kt):>3}" if ac.ground_speed_kt is not None else " --"
            is_sel = sel_icao and ac.icao == sel_icao.upper()
            it = classify(ac)
            marker = "⚠" if it.is_alert else ("▲" if ac.has_position() else "·")
            mcol = altitude_color(ac.altitude_ft, bool(ac.on_ground))
            row_txt = f" {marker} {label} FL{alt} {spd}kt"
            row_txt = (row_txt + " " * width)[:width]
            base = "class:panel.title.active" if is_sel else "class:panel.value"
            self.add_row([(base if is_sel else _hexstyle(mcol), row_txt)],
                         width, action=self._make_select(ac.icao))

    def _range_to(self, ac) -> str:
        if ac.lat is None or ac.lon is None:
            return ""
        st = self.ctx.state
        r_nm = 3440.065
        p1, p2 = math.radians(st.lat), math.radians(ac.lat)
        dphi = math.radians(ac.lat - st.lat)
        dl = math.radians(ac.lon - st.lon)
        a = (math.sin(dphi / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
        dist = 2 * r_nm * math.asin(min(1.0, math.sqrt(a)))
        y = math.sin(dl) * math.cos(p2)
        x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
        brg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
        return f"{dist:.1f} nm {_COMPASS[int((brg + 22.5) % 360 / 45)]}"

    def _make_select(self, icao: str):
        def fn():
            st = self.ctx.state
            cur = getattr(st, "selected_aircraft_icao", None)
            new = None if (cur and cur.upper() == icao.upper()) else icao.upper()
            if hasattr(st, "select_aircraft"):
                st.select_aircraft(new)
                self.ctx.rerender()
        return fn

    def _deselect(self) -> None:
        st = self.ctx.state
        if hasattr(st, "select_aircraft"):
            st.select_aircraft(None)
            self._ac()["follow_selected"] = False
            self.ctx.rerender()

    def _toggle_follow(self) -> None:
        st = self.ctx.state
        if not getattr(st, "selected_aircraft_icao", None):
            st.set_info("Follow: select an aircraft first")
            self.ctx.refresh()
            return
        self._toggle("follow_selected", default=False)

    def _follow_zoom(self) -> None:
        st = self.ctx.state
        if not getattr(st, "selected_aircraft_icao", None):
            st.set_info("Follow: select an aircraft first")
            self.ctx.refresh()
            return
        self._ac()["follow_selected"] = True
        if hasattr(st, "set_zoom"):
            st.set_zoom(_TRACK_ZOOM)
        self.ctx.rerender()

    def _center_on(self, ac) -> None:
        st = self.ctx.state
        if ac.has_position() and hasattr(st, "set_center"):
            pos = ac.projected_position() or (ac.lat, ac.lon)
            st.set_center(pos[0], pos[1])
            self.ctx.rerender()

def _on(v) -> str:
    return "on" if v else "off"
