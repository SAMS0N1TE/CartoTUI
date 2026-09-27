from __future__ import annotations

from cartotui import looks as L
from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class LooksWidget(Widget):
    """One-click gallery of curated visual presets ("Looks")."""

    name = "looks"
    title = "Preset library"
    default_width = 42
    default_top = 2
    default_left = 2
    default_visible = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._extras = False
        self._themes = False

    def build(self, width):
        from cartotui import theme_loader as T
        from cartotui.ui.widgets.theme_widget import ThemeWidget
        self.add_section("Start here", width)
        self.add_dim("Clean map styles; colours stay editable.", width)
        for key in ("terminal", "photo", "paper", "night"):
            lk = L.get_look(key)
            self.add_button(lk.name, width, self._make_apply(key))
            self.add_dim(lk.desc, width)
        self.add_section("My saved presets", width)
        names = [n for n in T.available_theme_names() if not T.resolve_theme(n).get("builtin")]
        editor = ThemeWidget(self.ctx)
        if not names:
            self.add_dim("Save your first preset in the editor.", width)
        for name in names:
            self.add_button(name, width, editor._make_apply(name))
        self.add_button("Edit colours / save preset", width, self._edit)
        if self.add_fold("Colour themes only", width, self._themes, self._toggle_themes):
            for name in T.available_theme_names():
                if T.resolve_theme(name).get("builtin"):
                    self.add_button(name, width, self._theme_only(name))
        if self.add_fold("Experimental text looks", width, self._extras, self._toggle_extras):
            for lk in L.LOOKS:
                if lk.key not in ("terminal", "photo", "paper", "night"):
                    self.add_button(lk.name, width, self._make_apply(lk.key))
                    self.add_dim(lk.summary(), width)

    def _toggle_extras(self):
        self._extras = not self._extras
        self.ctx.refresh()

    def _toggle_themes(self):
        self._themes = not self._themes
        self.ctx.refresh()

    def _edit(self):
        if self.ctx.manager and self.ctx.manager.open_settings:
            self.ctx.manager.open_settings("theme")

    def _theme_only(self, name):
        def apply():
            self.ctx.cfg.data["theme"] = {}
            self.ctx.state.theme = name
            self.ctx.cfg.update({"ui": {"theme": name}})
            if self.ctx.on_style_changed:
                self.ctx.on_style_changed()
            self.ctx.rerender()
        return apply

    def _make_apply(self, key: str):
        def fn():
            lk = L.get_look(key)
            if lk is None:
                return
            L.apply_look(self.ctx.state, self.ctx.cfg, lk)
            try:
                self.ctx.cfg.save()
            except Exception:
                pass
            self.ctx.state.set_info(f"Look → {lk.name}")
            if self.ctx.on_style_changed is not None:
                self.ctx.on_style_changed()
            else:
                self.ctx.rerender()
        return fn
