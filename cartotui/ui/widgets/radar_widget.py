from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class RadarWidget(Widget):
    name = "radar"
    title = "Radar"
    default_width = 32
    default_top = 15
    default_left = 2
    default_visible = False

    def _rd(self) -> dict:
        return self.ctx.cfg.get("overlays", {}).get("radar", {})

    def build(self, width: int) -> None:
        rd = self._rd()
        on = bool(rd.get("enabled"))
        animate = bool(rd.get("animate"))
        rs = getattr(self.ctx.map_control, "radar_source", None)
        self.add_kv("Weather radar", "on" if on else "off", width, action=self._toggle)
        self.add_kv("Animate", "on" if animate else "off", width, action=self._toggle_animate)
        if not animate:
            self.add_kv("Frame", rd.get("frame", "latest"), width, action=self._toggle_frame)
        self._num_row("Opacity", width)
        if on and rs is not None:
            if animate and rs.frame_count():
                label = f"{rs.anim_index() + 1}/{rs.frame_count()} {rs.frame_label()}"
            else:
                label = rs.frame_label()
        else:
            label = "off"
        self.add_kv("Updated", label, width)
        self.add_button("Refresh now", width, self._refresh)
        self.add_dim("data: RainViewer", width)

    def _toggle_animate(self) -> None:
        self._apply({"animate": not bool(self._rd().get("animate"))})

    def _refresh(self) -> None:
        import threading
        rs = getattr(self.ctx.map_control, "radar_source", None)

        def work():
            if rs is not None:
                rs.force_refresh()
            if self.ctx.request_render is not None:
                self.ctx.request_render()

        threading.Thread(target=work, daemon=True).start()
        self.ctx.refresh()

    def _num_row(self, label, width) -> None:
        rd = self._rd()
        minus, plus = "[-]", "[+]"
        val = f"{float(rd.get('opacity', 0.65)):.2f}"
        lbl = " " + (label or "adjust")
        right = len(minus) + 1 + len(val) + 1 + len(plus)
        gap = max(1, width - len(lbl) - right)
        y = len(self._lines)
        self._lines.append([
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            ("class:panel.button", minus),
            ("class:panel", " "),
            ("class:panel.value", val),
            ("class:panel", " "),
            ("class:panel.button", plus),
        ])
        x = len(lbl) + gap
        self._hits.append((y, x, x + len(minus), lambda: self._adj_opacity(-0.1)))
        xp0 = x + len(minus) + 1 + len(val) + 1
        self._hits.append((y, xp0, xp0 + len(plus), lambda: self._adj_opacity(0.1)))

    def _apply(self, patch: dict) -> None:
        self.ctx.cfg.update({"overlays": {"radar": patch}})
        try:
            self.ctx.cfg.save()
        except Exception:
            pass
        self.ctx.rerender()

    def _toggle(self) -> None:
        self._apply({"enabled": not bool(self._rd().get("enabled"))})

    def _toggle_frame(self) -> None:
        cur = self._rd().get("frame", "latest")
        self._apply({"frame": "nowcast" if cur == "latest" else "latest"})

    def _adj_opacity(self, d: float) -> None:
        cur = float(self._rd().get("opacity", 0.65))
        self._apply({"opacity": round(max(0.1, min(1.0, cur + d)), 2)})
