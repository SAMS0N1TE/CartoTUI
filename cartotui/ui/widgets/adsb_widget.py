from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class AdsbWidget(Widget):
    name = "adsb"
    title = "ADS-B"
    default_width = 36
    default_top = 2
    default_left = 26
    default_visible = False

    def build(self, width: int) -> None:
        get_traffic = self.ctx.get_traffic
        registry = self.ctx.aircraft_registry
        traffic = get_traffic() if get_traffic else None

        self.add_section("Link", width)
        if traffic is None:
            self.add_dim("not configured", width)
        else:
            st = traffic.status()
            self.add_kv("Status", "CONNECTED" if st.connected else "OFFLINE", width)
            self.add_kv("Source", st.name, width)
            age = st.age_s()
            if age is None:
                age_text = "never"
            elif age < 1.0:
                age_text = "now"
            elif age < 60.0:
                age_text = f"{age:.0f}s ago"
            else:
                age_text = f"{age / 60:.1f}m ago"
            self.add_kv("Last", age_text, width)
            self.add_kv("Msgs/s", f"{st.msgs_per_sec:.1f}", width)

        count = len(registry) if registry else 0
        self.add_section(f"Aircraft ({count})", width)
        if not registry or count == 0:
            self.add_dim("(none)", width)
            return

        sel = getattr(self.ctx.state, "selected_aircraft_icao", None)
        ac_list = registry.snapshot()
        ac_list.sort(key=lambda a: (not a.has_position(), (a.callsign or a.icao).strip()))
        for ac in ac_list[:8]:
            label = (ac.callsign or ac.icao)[:8].ljust(8)
            alt = f"{int(ac.altitude_ft / 100):>3}" if ac.altitude_ft is not None else " --"
            spd = f"{int(ac.ground_speed_kt):>3}" if ac.ground_speed_kt is not None else " --"
            marker = "!" if ac.emergency else ("▲" if ac.has_position() else "·")
            is_sel = sel and ac.icao == sel.upper()
            row = f" {marker} {label} FL{alt} {spd}kt"
            style = "class:panel.title.active" if is_sel else "class:panel.value"
            self.add_row([(style, (row + " " * width)[:width])], width,
                         action=self._make_select(ac.icao))

    def _make_select(self, icao: str):
        def fn():
            st = self.ctx.state
            cur = getattr(st, "selected_aircraft_icao", None)
            new = None if (cur and cur.upper() == icao.upper()) else icao.upper()
            if self.ctx.map_control is not None and hasattr(st, "select_aircraft"):
                st.select_aircraft(new)
                self.ctx.rerender()
        return fn
