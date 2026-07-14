from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_ARROWS = [
    (0, "↑"), (45, "↗"), (90, "→"), (135, "↘"),
    (180, "↓"), (225, "↙"), (270, "←"), (315, "↖"),
]


def _arrow_for(deg: float) -> str:
    deg = deg % 360
    return min(_ARROWS, key=lambda d: min(abs(d[0] - deg), 360 - abs(d[0] - deg)))[1]


def _cardinal(deg: float) -> str:
    deg = deg % 360
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg + 22.5) % 360 // 45)]


@register_widget
class CompassWidget(Widget):
    name = "compass"
    title = "Compass"
    default_width = 22
    default_top = 2
    default_left = 2
    default_visible = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        deg = getattr(st, "heading_deg", 0.0)
        arrow = _arrow_for(deg)
        self.add_text("    N", width, style="class:panel.label")
        self.add_text("  ╲ │ ╱", width, style="class:panel.label")
        self.add_row([
            ("class:panel.label", " W ─ "),
            ("class:panel.value", arrow),
            ("class:panel.label", " ─ E"),
        ], width)
        self.add_text("  ╱ │ ╲", width, style="class:panel.label")
        self.add_text("    S", width, style="class:panel.label")
        self.add_blank(width)
        self.add_kv("Heading", f"{_cardinal(deg)} {deg:03.0f}°", width)
        self.add_kv("Zoom", f"z{getattr(st, 'z', 0)}", width)
        self.add_kv("Lat", f"{getattr(st, 'lat', 0.0):+.4f}", width)
        self.add_kv("Lon", f"{getattr(st, 'lon', 0.0):+.4f}", width)
