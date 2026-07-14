from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_QUALITY = {2: "fastest", 3: "fast", 4: "balanced", 6: "sharp", 8: "max"}


@register_widget
class RenderWidget(Widget):
    name = "render"
    title = "Render"
    default_width = 30
    default_top = 1
    default_left = 30
    default_visible = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        r = self.ctx.cfg["render"]
        self.add_section("Vector", width)
        self.add_kv("Engine", r.get("vector_engine", "libcarto"), width, action=self._toggle_engine)
        self.add_kv("View", st.render_mode, width, action=self._cycle_mode)
        self.add_kv("Roads", "highlight" if r.get("road_highlight") else "normal",
                    width, action=self._toggle_roads)
        self.add_kv("Boundaries", "on" if r.get("boundaries", True) else "off",
                    width, action=self._toggle_boundaries)
        self.add_kv("Raster", "theme tint" if r.get("raster_tint") == "theme" else "real colours",
                    width, action=self._toggle_tint)
        self.add_kv("Pan quality", "dynamic" if r.get("dynamic_quality", True) else "full",
                    width, action=self._toggle_dynamic)
        self.add_kv("Colours", {"truecolor": "truecolor", "256": "256 (faster)",
                                "16": "16 (fastest)"}.get(r.get("color_depth", "truecolor"),
                                                          r.get("color_depth", "truecolor")),
                    width, action=self._cycle_depth)
        scale = int(r.get("vector_scale", 6))
        self.add_kv("Quality", _QUALITY.get(scale, str(scale)), width, action=self._cycle_quality)
        self.add_section("Image", width)
        self.add_kv("Color", "on" if st.color else "off", width, action=self._toggle_color)
        self.add_kv("Palette", st.palette, width, action=self._cycle_palette)
        self.add_kv("Dither", st.dither, width, action=self._cycle_dither)

    def _apply(self, patch: dict) -> None:
        self.ctx.cfg.update(patch)
        try:
            self.ctx.cfg.save()
        except Exception:
            pass
        self.ctx.rerender()

    def _toggle_engine(self) -> None:
        cur = self.ctx.cfg["render"].get("vector_engine", "libcarto")
        self._apply({"render": {"vector_engine": "python" if cur == "libcarto" else "libcarto"}})

    def _cycle_mode(self) -> None:
        self.ctx.state.cycle_render_mode()
        self.ctx.rerender()

    def _toggle_roads(self) -> None:
        cur = bool(self.ctx.cfg["render"].get("road_highlight", False))
        self._apply({"render": {"road_highlight": not cur}})

    def _toggle_boundaries(self) -> None:
        cur = bool(self.ctx.cfg["render"].get("boundaries", True))
        self._apply({"render": {"boundaries": not cur}})

    def _toggle_tint(self) -> None:
        cur = self.ctx.cfg["render"].get("raster_tint", "none")
        self._apply({"render": {"raster_tint": "none" if cur == "theme" else "theme"}})

    def _toggle_dynamic(self) -> None:
        cur = bool(self.ctx.cfg["render"].get("dynamic_quality", True))
        self._apply({"render": {"dynamic_quality": not cur}})

    def _cycle_depth(self) -> None:
        order = ["truecolor", "256", "16"]
        cur = self.ctx.cfg["render"].get("color_depth", "truecolor")
        i = order.index(cur) if cur in order else 0
        self.ctx.cfg.update({"render": {"color_depth": order[(i + 1) % len(order)]}})
        try:
            self.ctx.cfg.save()
        except Exception:
            pass
        self.ctx.refresh()

    def _cycle_quality(self) -> None:
        order = [3, 4, 6, 8]
        cur = int(self.ctx.cfg["render"].get("vector_scale", 6))
        i = order.index(cur) if cur in order else 2
        self._apply({"render": {"vector_scale": order[(i + 1) % len(order)]}})

    def _toggle_color(self) -> None:
        self.ctx.state.toggle_color()
        self.ctx.rerender()

    def _cycle_palette(self) -> None:
        from cartotui.rendering.renderer import default_palettes
        self.ctx.state.cycle_palette(list(default_palettes().keys()))
        self.ctx.rerender()

    def _cycle_dither(self) -> None:
        self.ctx.state.cycle_dither()
        self.ctx.rerender()
