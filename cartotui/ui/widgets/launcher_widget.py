from __future__ import annotations

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget


@register_widget
class LauncherWidget(Widget):
    name = "widgets"
    title = "Widgets"
    default_width = 28
    default_top = 2
    default_left = 2
    default_visible = False

    def build(self, width: int) -> None:
        mgr = self.ctx.manager
        self.add_section("Panels", width)
        if mgr is None:
            self.add_dim("no manager", width)
            return
        for name in mgr.all_names():
            if name == self.name:
                continue
            panel = mgr.panel(name)
            title = panel.widget.title if panel else name
            on = mgr.is_visible(name)
            state = "[on] " if on else "[off]"
            self.add_row([
                ("class:panel.ok" if on else "class:panel.dim", " " + state + " "),
                ("class:panel.value", title),
            ], width, action=self._make_toggle(name))
        self.add_section("Layout", width)
        self.add_button("Reset positions", width, mgr.reset_layout)

        self.add_section("Profile", width)
        self.add_button("Save profile (loads on boot)", width, self._save_profile)

    def _save_profile(self) -> None:
        if self.ctx.save_profile is not None:
            self.ctx.save_profile()

    def _make_toggle(self, name: str):
        def fn():
            if self.ctx.manager is not None:
                self.ctx.manager.toggle(name)
        return fn
