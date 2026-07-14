from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class StatsWidget(Widget):
    name = "stats"
    title = "Stats"
    default_width = 26
    default_top = 15
    default_left = 40
    default_visible = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        r = self.ctx.cfg["render"]
        self.add_kv("Render", f"{st.last_render_ms:.0f} ms", width)
        load = 0
        try:
            from cartotui.rendering.libcarto_backend import get_loading
            load = get_loading()
        except Exception:
            load = 0
        self.add_kv("Loading", str(load), width)
        self.add_kv("Engine", r.get("vector_engine", "libcarto"), width)
        self.add_kv("Source", st.source, width)
        self.add_kv("View", st.render_mode, width)
        self.add_kv("Theme", st.theme, width)
