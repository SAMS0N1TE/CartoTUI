from __future__ import annotations

from typing import Dict, List, Optional

from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.layout import Float

from cartotui.ui.widgets.base import WidgetContext
from cartotui.ui.widgets.panel import Panel
from cartotui.ui.widgets.registry import create_widget, widget_names


class WidgetManager:
    def __init__(self, ctx: WidgetContext, order: Optional[List[str]] = None) -> None:
        self.ctx = ctx
        ctx.manager = self
        self._float_container = None
        self._base_floats: List[Float] = []
        self.screen_w = 120
        self.screen_h = 40
        self._panels: Dict[str, Panel] = {}
        self._order: List[str] = []
        self._visible: Dict[str, bool] = {}
        self._drag: Optional[dict] = None

        names = order or widget_names()
        for name in names:
            w = create_widget(name, ctx)
            if w is None:
                continue
            panel = Panel(
                w, self,
                top=getattr(w, "default_top", 2),
                left=getattr(w, "default_left", 2),
                width=getattr(w, "default_width", 30),
            )
            self._panels[name] = panel
            self._order.append(name)
            self._visible[name] = bool(getattr(w, "default_visible", False))

        self.load_layout()

    def attach(self, float_container, base_floats: List[Float]) -> None:
        self._float_container = float_container
        self._base_floats = list(base_floats)
        self.rebuild()

    def set_screen(self, w: int, h: int) -> None:
        if w > 0 and h > 0:
            self.screen_w = w
            self.screen_h = h

    def _refresh_screen(self) -> None:
        mc = self.ctx.map_control
        if mc is not None:
            w = getattr(mc, "_last_w", 0)
            h = getattr(mc, "_last_h", 0)
            self.set_screen(w, h)

    def panel(self, name: str) -> Optional[Panel]:
        return self._panels.get(name)

    def all_names(self) -> List[str]:
        return list(self._order)

    def is_visible(self, name: str) -> bool:
        return bool(self._visible.get(name))

    def _clamp(self, panel: Panel, top: int, left: int):
        max_left = max(0, self.screen_w - 6)
        max_top = max(1, self.screen_h - 2)
        return max(1, min(max_top, int(top))), max(0, min(max_left, int(left)))

    def move_panel(self, panel: Panel, top: int, left: int) -> None:
        self._refresh_screen()
        panel.top, panel.left = self._clamp(panel, top, left)
        if panel.float is not None:
            panel.float.top = panel.top
            panel.float.left = panel.left
        self.invalidate()

    def begin_drag(self, panel: Panel, grab_x: int, grab_y: int) -> None:
        self._drag = {"panel": panel, "gx": int(grab_x), "gy": int(grab_y)}
        self.bring_to_front(panel)

    def is_dragging(self) -> bool:
        return self._drag is not None

    def drag_to(self, abs_x: int, abs_y: int) -> None:
        d = self._drag
        if not d:
            return
        self.move_panel(d["panel"], abs_y - d["gy"], abs_x - d["gx"])

    def end_drag(self, save: bool = True) -> None:
        if self._drag is not None:
            self._drag = None
            if save:
                self.save_layout()

    def bring_to_front(self, panel: Panel) -> None:
        if self._order and self._order[-1] == panel.name:
            return
        if panel.name in self._order:
            self._order.remove(panel.name)
            self._order.append(panel.name)
            self.rebuild()

    def show(self, name: str) -> None:
        if name in self._panels:
            panel = self._panels[name]
            self._visible[name] = True
            self._refresh_screen()
            panel.top, panel.left = self._clamp(panel, panel.top, panel.left)
            if panel.float is not None:
                panel.float.top = panel.top
                panel.float.left = panel.left
            if name in self._order:
                self._order.remove(name)
                self._order.append(name)
            self.rebuild()
            self.save_layout()

    def hide(self, name: str) -> None:
        if name in self._panels:
            self._visible[name] = False
            self.rebuild()
            self.save_layout()

    def toggle(self, name: str) -> None:
        if self.is_visible(name):
            self.hide(name)
        else:
            self.show(name)

    def reset_layout(self) -> None:
        for name, panel in self._panels.items():
            w = panel.widget
            panel.top = getattr(w, "default_top", 2)
            panel.left = getattr(w, "default_left", 2)
            panel.width = getattr(w, "default_width", 30)
            panel.collapsed = False
            self._visible[name] = bool(getattr(w, "default_visible", False))
        self.rebuild()
        self.save_layout()

    def _ensure_float(self, panel: Panel) -> Float:
        if panel.float is None:
            panel.float = Float(
                content=panel.window,
                top=panel.top,
                left=panel.left,
                width=(lambda p=panel: p.width),
                height=(lambda p=panel: p.height()),
            )
        else:
            panel.float.top = panel.top
            panel.float.left = panel.left
        return panel.float

    def build_floats(self) -> List[Float]:
        floats: List[Float] = []
        for name in self._order:
            if not self._visible.get(name):
                continue
            floats.append(self._ensure_float(self._panels[name]))
        return floats

    def rebuild(self) -> None:
        if self._float_container is None:
            return
        self._float_container.floats = list(self._base_floats) + self.build_floats()
        self.invalidate()

    def invalidate(self) -> None:
        app = get_app_or_none()
        if app is not None:
            app.invalidate()

    def save_layout(self) -> None:
        panels = []
        for name in self._order:
            panel = self._panels[name]
            panels.append({
                "name": name,
                "top": panel.top,
                "left": panel.left,
                "width": panel.width,
                "collapsed": panel.collapsed,
                "visible": bool(self._visible.get(name)),
            })
        try:
            self.ctx.cfg.update({"ui": {"panels": panels}})
            self.ctx.cfg.save()
        except Exception:
            pass

    def load_layout(self) -> None:
        try:
            saved = self.ctx.cfg["ui"].get("panels", [])
        except Exception:
            saved = []
        if not isinstance(saved, list):
            return
        seen = []
        for entry in saved:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            panel = self._panels.get(name)
            if panel is None:
                continue
            try:
                panel.top = int(entry.get("top", panel.top))
                panel.left = int(entry.get("left", panel.left))
                panel.width = max(16, int(entry.get("width", panel.width)))
                panel.window.width = panel.width
                panel.collapsed = bool(entry.get("collapsed", panel.collapsed))
                self._visible[name] = bool(entry.get("visible", self._visible.get(name)))
            except (TypeError, ValueError):
                continue
            seen.append(name)
        remaining = [n for n in self._order if n not in seen]
        self._order = seen + remaining
