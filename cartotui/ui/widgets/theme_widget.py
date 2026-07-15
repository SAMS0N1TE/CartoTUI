from __future__ import annotations

import os
from typing import Dict, Optional

from cartotui import theme_loader
from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_UI_CORE = ("bg", "fg", "dim", "accent", "key", "section", "border",
            "panel_bg", "title_bg", "title_fg", "sel_bg", "sel_fg", "warn", "ok")

_EDIT_FIELDS = [
    ("Background", "bg"),
    ("Text", "fg"),
    ("Accent", "accent"),
    ("Roads", "road"),
    ("Water", "water"),
    ("Labels", "label"),
]

@register_widget
class ThemeWidget(Widget):
    name = "theme"
    title = "Themes"
    default_width = 40
    default_top = 2
    default_left = 62
    default_visible = False

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._cache_name: Optional[str] = None
        self._cache_data: Dict = {}

    def _current(self) -> str:
        return getattr(self.ctx.state, "theme", None) or self.ctx.cfg["ui"].get("theme", "amber")

    def _editable_data(self, name: str) -> Dict:
        if self._cache_name == name and self._cache_data:
            return self._cache_data
        path = theme_loader.theme_source_path(name)
        userdir = theme_loader.user_theme_dir()
        data: Dict = {}
        if path and os.path.normpath(os.path.dirname(path)) == os.path.normpath(userdir):
            try:
                import json
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if not data:
            t = theme_loader.resolve_theme(name)
            ui = t["ui"]
            m = t["map"] if isinstance(t.get("map"), dict) else {}
            data = {
                "name": name,
                "border": t.get("border", "auto"),
                "ui": {k: ui[k] for k in _UI_CORE if k in ui},
                "map": dict(m),
            }
        data.setdefault("ui", {})
        data.setdefault("map", {})
        rt = theme_loader.resolve_theme(name)
        for k in _UI_CORE:
            data["ui"].setdefault(k, rt["ui"].get(k, "#808080"))
        for k, dflt in (("bg", data["ui"]["bg"]), ("water", "#5f6978"),
                        ("park", "#3c503c"), ("building", "#4b4b50"),
                        ("road", data["ui"]["fg"]), ("label", data["ui"]["accent"]),
                        ("halo", "#000000")):
            data["map"].setdefault(k, dflt)
        self._cache_name = name
        self._cache_data = data
        return data

    def _field_value(self, data: Dict, key: str) -> str:
        if key in ("bg", "fg", "accent"):
            return data["ui"].get(key, "#808080")
        return data["map"].get(key, "#808080")

    def build(self, width: int) -> None:
        cur = self._current()

        self.add_section("Select theme", width)
        for name in theme_loader.available_theme_names():
            t = theme_loader.resolve_theme(name)
            mark = "●" if name == cur else "○"
            tag = "" if t.get("builtin") else " *"
            self.add_row([
                ("class:panel.hotkey", " " + mark + " "),
                ("class:panel.value" if name == cur else "class:panel.label", name + tag),
            ], width, action=self._make_apply(name))

        self.add_section(f"Customize {cur}", width)
        data = self._editable_data(cur)
        for label, key in _EDIT_FIELDS:
            self._color_row(label, key, data, width)

        self.add_section("Preset (live)", width)
        st = self.ctx.state
        self._num_row("Brightness", f"{st.brightness:+.2f}", width,
                      lambda: self._adj_brightness(-0.1), lambda: self._adj_brightness(0.1))
        self._num_row("Contrast", f"{st.contrast:+.2f}", width,
                      lambda: self._adj_contrast(-0.1), lambda: self._adj_contrast(0.1))
        self.add_kv("Dither", st.dither, width, action=self._cycle_dither)
        self.add_kv("Palette", st.palette, width, action=self._cycle_palette)
        self.add_kv("View", st.render_mode, width, action=self._cycle_view)
        r = self.ctx.cfg["render"]
        self._num_row("Road width", f"{float(r.get('road_thickness', 1.0)):.2f}x", width,
                      lambda: self._adj_road(-0.1), lambda: self._adj_road(0.1))
        _mode = st.render_mode
        _bm = r.get("road_thickness_by_mode") or {}
        self._num_row(f"  in {_mode}", f"{float(_bm.get(_mode, 1.0)):.2f}x", width,
                      lambda: self._adj_road_mode(-0.1), lambda: self._adj_road_mode(0.1))
        self.add_kv("Roads", "highlight" if r.get("road_highlight") else "normal",
                    width, action=self._toggle_roads)
        self.add_kv("Raster", "tint" if r.get("raster_tint") == "theme" else "real",
                    width, action=self._toggle_tint)

        self.add_section("Manage", width)
        self.add_button("Save preset to this theme", width, self._save_preset)
        self.add_button("Save as new theme", width, self._duplicate)
        userdir = theme_loader.user_theme_dir()
        path = theme_loader.theme_source_path(cur)
        is_user = bool(path and os.path.normpath(os.path.dirname(path)) == os.path.normpath(userdir))
        if is_user:
            self.add_button("Delete this theme", width, self._reset_current)
        self.add_dim(f"folder: {userdir}", width)

    def _num_row(self, label, value, width, on_minus, on_plus) -> None:
        minus, plus = "[-]", "[+]"
        lbl = " " + label
        right = len(minus) + 1 + len(value) + 1 + len(plus)
        gap = max(1, width - len(lbl) - right)
        y = len(self._lines)
        self._lines.append([
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            ("class:panel.button", minus),
            ("class:panel", " "),
            ("class:panel.value", value),
            ("class:panel", " "),
            ("class:panel.button", plus),
        ])
        x = len(lbl) + gap
        self._hits.append((y, x, x + len(minus), on_minus))
        xp0 = x + len(minus) + 1 + len(value) + 1
        self._hits.append((y, xp0, xp0 + len(plus), on_plus))

    def _adj_brightness(self, d) -> None:
        self.ctx.state.adjust_brightness(d)
        self.ctx.rerender()

    def _adj_contrast(self, d) -> None:
        self.ctx.state.adjust_contrast(d)
        self.ctx.rerender()

    def _cycle_dither(self) -> None:
        self.ctx.state.cycle_dither()
        self.ctx.rerender()

    def _cycle_palette(self) -> None:
        from cartotui.rendering.renderer import default_palettes
        self.ctx.state.cycle_palette(list(default_palettes().keys()))
        self.ctx.rerender()

    def _cycle_view(self) -> None:
        self.ctx.state.cycle_render_mode()
        self.ctx.rerender()

    def _adj_road(self, d) -> None:
        cur = float(self.ctx.cfg["render"].get("road_thickness", 1.0) or 1.0)
        self.ctx.cfg.update({"render": {
            "road_thickness": round(max(0.2, min(4.0, cur + d)), 2)}})
        self._save_cfg()
        self.ctx.rerender()

    def _adj_road_mode(self, d) -> None:
        r = self.ctx.cfg["render"]
        mode = self.ctx.state.render_mode
        by_mode = dict(r.get("road_thickness_by_mode") or {})
        cur = float(by_mode.get(mode, 1.0) or 1.0)
        by_mode[mode] = round(max(0.2, min(4.0, cur + d)), 2)
        self.ctx.cfg.update({"render": {"road_thickness_by_mode": by_mode}})
        self._save_cfg()
        self.ctx.rerender()

    def _toggle_roads(self) -> None:
        cur = bool(self.ctx.cfg["render"].get("road_highlight", False))
        self.ctx.cfg.update({"render": {"road_highlight": not cur}})
        self._save_cfg()
        self.ctx.rerender()

    def _toggle_tint(self) -> None:
        cur = self.ctx.cfg["render"].get("raster_tint", "none")
        self.ctx.cfg.update({"render": {"raster_tint": "none" if cur == "theme" else "theme"}})
        self._save_cfg()
        self.ctx.rerender()

    def _save_cfg(self) -> None:
        try:
            self.ctx.cfg.save()
        except Exception:
            pass

    def _current_preset(self) -> dict:
        st = self.ctx.state
        r = self.ctx.cfg["render"]
        return {
            "brightness": round(st.brightness, 2),
            "contrast": round(st.contrast, 2),
            "dither": st.dither,
            "palette": st.palette,
            "view": st.render_mode,
            "road_highlight": bool(r.get("road_highlight", False)),
            "raster_tint": r.get("raster_tint", "none"),
            "road_thickness": float(r.get("road_thickness", 1.0)),
            "road_thickness_by_mode": dict(r.get("road_thickness_by_mode") or {}),
        }

    def _save_preset(self) -> None:
        cur = self._current()
        data = dict(self._editable_data(cur))
        data["ui"] = dict(data["ui"])
        data["map"] = dict(data["map"])
        data["render"] = self._current_preset()
        theme_loader.save_user_theme(cur, data)
        self._cache_name = None
        self.ctx.state.theme = cur
        if self.ctx.on_theme_changed:
            self.ctx.on_theme_changed()
        self.ctx.rerender()

    def _color_row(self, label: str, key: str, data: Dict, width: int) -> None:
        val = self._field_value(data, key)
        minus, plus, sw = "[-]", "[+]", " ██ "
        lbl = " " + label
        right = len(minus) + len(sw) + len(val) + len(plus)
        gap = max(1, width - len(lbl) - right)
        y = len(self._lines)
        self._lines.append([
            ("class:panel.label", lbl),
            ("class:panel", " " * gap),
            ("class:panel.button", minus),
            (f"fg:{val}", sw),
            ("class:panel.value", val),
            ("class:panel.button", plus),
        ])
        x = len(lbl) + gap
        xm0, xm1 = x, x + len(minus)
        xp0 = xm1 + len(sw) + len(val)
        xp1 = xp0 + len(plus)
        self._hits.append((y, xm0, xm1, self._make_edit(key, -8)))
        self._hits.append((y, xp0, xp1, self._make_edit(key, +8)))

    def _make_apply(self, name: str):
        def fn():
            self.ctx.state.theme = name
            self.ctx.cfg.update({"ui": {"theme": name}})
            if self.ctx.on_theme_changed:
                self.ctx.on_theme_changed()
            self._cache_name = None
            self.ctx.rerender()
        return fn

    def _make_edit(self, key: str, delta: int):
        def fn():
            cur = self._current()
            data = dict(self._editable_data(cur))
            data["ui"] = dict(data["ui"])
            data["map"] = dict(data["map"])
            val = self._field_value(data, key)
            newval = theme_loader._shade(val, delta)
            if key == "bg":
                data["ui"]["bg"] = newval
                data["map"]["bg"] = newval
            elif key in ("fg", "accent"):
                data["ui"][key] = newval
            else:
                data["map"][key] = newval
            theme_loader.save_user_theme(cur, data)
            self._cache_name = None
            self.ctx.state.theme = cur
            if self.ctx.on_theme_changed:
                self.ctx.on_theme_changed()
            self.ctx.rerender()
        return fn

    def _duplicate(self) -> None:
        cur = self._current()
        base = self._editable_data(cur)
        existing = set(theme_loader.available_theme_names())
        i = 1
        while f"custom{i}" in existing:
            i += 1
        newname = f"custom{i}"
        data = {"name": newname, "border": base.get("border", "auto"),
                "ui": dict(base["ui"]), "map": dict(base["map"]),
                "render": self._current_preset()}
        theme_loader.save_user_theme(newname, data)
        self._cache_name = None
        self.ctx.state.theme = newname
        self.ctx.cfg.update({"ui": {"theme": newname}})
        if self.ctx.on_theme_changed:
            self.ctx.on_theme_changed()
        self.ctx.rerender()

    def _reset_current(self) -> None:
        cur = self._current()
        theme_loader.delete_user_theme(cur)
        self._cache_name = None
        remaining = theme_loader.available_theme_names()
        newname = cur if cur in remaining else (remaining[0] if remaining else "amber")
        self.ctx.state.theme = newname
        self.ctx.cfg.update({"ui": {"theme": newname}})
        if self.ctx.on_theme_changed:
            self.ctx.on_theme_changed()
        self.ctx.rerender()
