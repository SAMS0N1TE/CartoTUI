from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class LocationWidget(Widget):
    name = "location"
    title = "Location"
    default_width = 28
    default_top = 1
    default_left = 62
    default_visible = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        self.add_kv("Lat", f"{st.lat:+.4f}", width)
        self.add_kv("Lon", f"{st.lon:+.4f}", width)
        self.add_kv("Zoom", f"z{st.z}", width)
        self.add_kv("Heading", f"{st.heading_deg:.0f}°", width)
        self.add_blank(width)
        self.add_button("Zoom in", width, self._zin)
        self.add_button("Zoom out", width, self._zout)
        self.add_button("Home", width, self._home)

    def _zin(self) -> None:
        if self.ctx.map_control is not None:
            self.ctx.map_control.zoom(+1)

    def _zout(self) -> None:
        if self.ctx.map_control is not None:
            self.ctx.map_control.zoom(-1)

    def _home(self) -> None:
        mc = self.ctx.map_control
        cfg = self.ctx.cfg
        if mc is not None:
            mc.goto(float(cfg["map"]["center_lat"]),
                    float(cfg["map"]["center_lon"]),
                    int(cfg["map"]["zoom"]))
