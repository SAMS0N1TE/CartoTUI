from __future__ import annotations

from cartotui import looks as L
from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class LooksWidget(Widget):
    """One-click gallery of curated visual presets ("Looks")."""

    name = "looks"
    title = "Looks"
    default_width = 42
    default_top = 2
    default_left = 2
    default_visible = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        cfg = self.ctx.cfg
        active = L.current_look_key(st, cfg)

        self.add_section("Pick a look", width)
        for lk in L.LOOKS:
            is_active = (lk.key == active)
            mark = "●" if is_active else "○"
            name_cls = "class:panel.value" if is_active else "class:panel.label"
            self.add_row([
                ("class:panel.hotkey", " " + mark + " "),
                (name_cls, lk.name),
            ], width, action=self._make_apply(lk.key))
            self.add_row([
                ("class:panel.dim", "   " + self._pad(lk.desc, width - 3)),
            ], width)

        self.add_section("Now showing", width)
        if active:
            self.add_kv("Look", L.get_look(active).name, width)
        else:
            self.add_kv("Look", "Custom", width)
        self.add_dim("Tip: press  l  to cycle looks", width)

        r = cfg["render"]
        notes = L.describe_incompatibilities(
            render_mode=st.render_mode, color=st.color, dither=st.dither,
            threshold=st.threshold_mode, invert=bool(r.get("invert", False)),
            palette=st.palette,
        )
        if notes and active is None:
            self.add_section("Heads up", width)
            for n in notes[:3]:
                self.add_row([("class:panel.warn", " ⚠ "),
                              ("class:panel.dim", self._pad(n, width - 3))], width)

    def _make_apply(self, key: str):
        def fn():
            lk = L.get_look(key)
            if lk is None:
                return
            theme_changed = L.apply_look(self.ctx.state, self.ctx.cfg, lk)
            try:
                self.ctx.cfg.save()
            except Exception:
                pass
            self.ctx.state.set_info(f"Look → {lk.name}")
            if theme_changed and self.ctx.on_theme_changed is not None:
                self.ctx.on_theme_changed()
            else:
                self.ctx.rerender()
        return fn
