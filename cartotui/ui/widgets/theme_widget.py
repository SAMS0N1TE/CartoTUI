from __future__ import annotations

import re
from copy import deepcopy

from cartotui import theme_loader as T
from cartotui.presets import apply_settings, capture_settings, preset_name
from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.input_dialog import ask_text
from cartotui.ui.widgets.registry import register_widget

MAP_FIELDS = (("Labels", "label"), ("Label backing", "halo"), ("Land", "bg"),
              ("Roads", "road"), ("Water", "water"), ("Parks", "park"),
              ("Buildings", "building"), ("Boundaries", "boundary"), ("Aircraft", "aircraft"))
UI_FIELDS = (("Panel", "settings_bg"), ("Text", "settings_fg"), ("Accent", "settings_accent"),
             ("Selected row", "settings_sel_bg"), ("Selected text", "settings_sel_fg"), ("Borders", "settings_dim"))
SWATCHES = (("White", "#eeeeee"), ("Black", "#121212"), ("Grey", "#889099"),
            ("Red", "#ed7777"), ("Amber", "#ffcc77"), ("Green", "#8fd694"),
            ("Cyan", "#77d8df"), ("Blue", "#80adff"), ("Violet", "#bd9bff"), ("Pink", "#ee9ac1"))


def parse_color(value):
    value = value.strip().lower()
    value = dict((n.lower(), c) for n, c in SWATCHES).get(value, value)
    value = value.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{3}", value):
        value = "".join(c*2 for c in value)
    if not re.fullmatch(r"[0-9a-f]{6}", value):
        raise ValueError("Enter #RRGGBB, #RGB or a colour name.")
    return "#" + value


@register_widget
class ThemeWidget(Widget):
    name = "theme"
    title = "Preset editor"
    default_width = 42
    default_top = 2
    default_left = 62
    default_visible = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._group = "map"
        self._editing = None
        self._undo = None
        self._undo_backing = None
        self._base_name = self._current()

    def _current(self):
        return self.ctx.state.theme

    def _editable_data(self, name):
        t = T.resolve_theme(name)
        data = {"name": name, "border": t.get("border", "auto"),
                "ui": deepcopy(t["ui"]), "map": deepcopy(t["map"]),
                "chrome": deepcopy(t.get("chrome_overrides", {}))}
        custom = self.ctx.cfg.data.get("theme", {})
        data["ui"].update(custom.get("ui", {}))
        data["map"].update({k: v for k, v in custom.items() if k in T.MAP_KEYS})
        if "road" in custom:
            data["map"]["roads"] = {}
        from cartotui.themes import _coerce_rgb
        for key, value in custom.get("road_colors", {}).items():
            rgb = _coerce_rgb(value)
            if rgb is not None:
                data["map"].setdefault("roads", {})[str(key)] = "#%02x%02x%02x" % rgb
        data["map"].setdefault("boundary", T._blend(
            data["map"].get("label", data["ui"]["accent"]), data["map"].get("bg", data["ui"]["bg"]), .5))
        data["chrome"].update(custom.get("chrome", {}))
        return data

    def _value(self, group, key):
        return self._editable_data(self._current())[group].get(key, "#808080")

    def build(self, width):
        if self._base_name != self._current():
            self._base_name = self._current()
            self._undo = None
            self._editing = None
        if self._editing:
            self._build_picker(width)
            return
        self.add_section("Your preset", width)
        self.add_kv("Base", self._current(), width)
        self.add_dim("Colours preview live; save when ready.", width)
        self.add_button("Save as named preset...", width, self._duplicate)
        if not T.resolve_theme(self._current()).get("builtin"):
            self.add_button("Update saved preset", width, self._save_preset)
            self.add_button("Rename preset...", width, self._rename)
        if self._undo is not None:
            self.add_button("Undo colour edits", width, self._revert)
        data = self._editable_data(self._current())
        for group, title, fields in (("map", "Map colours", MAP_FIELDS), ("ui", "Interface colours", UI_FIELDS)):
            if self.add_fold(title, width, self._group == group,
                             lambda g=group: self._set_group(g)):
                for label, key in fields:
                    value = data[group].get(key, "#808080")
                    self.add_kv(label, value, width,
                                action=lambda g=group, k=key, label=label: self._open_picker(g, k, label))
        self.add_section("Labels", width)
        self.add_kv("Names", "on" if self.ctx.state.labels else "off", width, action=self._toggle_labels)
        bg = self.ctx.cfg["render"].get("label_background", "auto")
        self.add_kv("Backing", bg, width, action=self._cycle_backing)
        self.add_button("Map detail / tone settings", width, lambda: self._open_page("render"))
        self.add_button("Browse presets", width, lambda: self._open_page("looks"))
        self.add_dim("Saves colours, labels, geometry & tone.", width)

    def _open_page(self, page):
        if self.ctx.manager and self.ctx.manager.open_settings:
            self.ctx.manager.open_settings(page)

    def _set_group(self, group):
        self._group = "" if self._group == group else group
        self.ctx.refresh()

    def _open_picker(self, group, key, label):
        self._editing = (group, key, label)
        self.ctx.refresh()

    def _build_picker(self, width):
        group, key, label = self._editing
        value = self._value(group, key)
        self.add_button("Back to preset", width, self._back)
        self.add_section(label, width)
        self.add_row([(f"bg:{value} fg:#000000", "   "), ("class:panel.value", " " + value)], width)
        self.add_button("Type hex / colour name...", width,
                        lambda: ask_text(self.ctx, label, "#RRGGBB, #RGB or colour name", value,
                                         lambda v: self._set_color(group, key, v)))
        for name, color in SWATCHES:
            self.add_row([(f"fg:{color}", " ██ "), ("class:panel.label", name)], width,
                         action=lambda c=color: self._set_color(group, key, c))
        rgb = T._hex_to_rgb(value)
        for index, channel in enumerate(("Red", "Green", "Blue")):
            self.add_adjust(channel, str(rgb[index]), width,
                            lambda i=index: self._channel(group, key, i, -8),
                            lambda i=index: self._channel(group, key, i, 8))
        self.add_button("Reset this colour", width, lambda: self._set_color(
            group, key, T.resolve_theme(self._current())[group].get(key, "#808080")))
        if key == "label":
            from cartotui.ui.map_overlay import _inverse_color
            backing = self.ctx.cfg["render"].get("label_background", "auto")
            bg = self._value("map", "halo" if backing == "theme" else "bg")
            if backing == "auto":
                bg = "#%02x%02x%02x" % _inverse_color(T._hex_to_rgb(value))
            def lum(color):
                rgb = [v/255 for v in T._hex_to_rgb(color)]
                return sum(w*(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)
                           for w, v in zip((.2126, .7152, .0722), rgb))
            a, b = sorted((lum(value), lum(bg)))
            contrast = (b+.05)/(a+.05)
            self.add_dim(f"Label contrast {contrast:.1f}:1" + (" - low" if contrast < 4.5 else ""), width)
            self.add_row([(f"fg:{value} bg:{bg}", " Sample town / Main Street ")], width)

    def _back(self):
        self._editing = None
        self.ctx.refresh()

    def _channel(self, group, key, index, delta):
        rgb = list(T._hex_to_rgb(self._value(group, key)))
        rgb[index] = max(0, min(255, rgb[index] + delta))
        self._set_color(group, key, "#%02x%02x%02x" % tuple(rgb))

    def _set_color(self, group, key, value):
        value = parse_color(value)
        custom = self.ctx.cfg.data.setdefault("theme", {})
        if self._undo is None:
            self._undo = deepcopy(custom)
            self._undo_backing = self.ctx.cfg["render"].get("label_background", "auto")
        if group == "ui":
            custom.setdefault("ui", {})[key] = value
        else:
            custom[key] = value
            if key == "road":
                custom["road_colors"] = {}
            if key == "halo":
                self.ctx.cfg.update({"render": {"label_background": "theme"}})
        self._refresh_style()

    def _refresh_style(self):
        if self.ctx.on_style_changed:
            self.ctx.on_style_changed()
        self.ctx.rerender()

    def _revert(self):
        self.ctx.cfg.data["theme"] = self._undo
        self.ctx.cfg.update({"render": {"label_background": self._undo_backing}})
        self._undo = None
        self._refresh_style()

    def _toggle_labels(self):
        self.ctx.state.toggle_labels()
        self.ctx.rerender()

    def _cycle_backing(self):
        options = ("auto", "theme", "none")
        cur = self.ctx.cfg["render"].get("label_background", "auto")
        self.ctx.cfg.update({"render": {"label_background": options[(options.index(cur)+1) % 3]}})
        self.ctx.rerender()

    def _current_preset(self):
        return capture_settings(self.ctx.state, self.ctx.cfg)

    def _save_as(self, name, rename=False, overwrite=False):
        name = preset_name(name)
        old = self._current()
        if name in T.available_theme_names() and not overwrite:
            raise ValueError("That name already exists. Choose another.")
        data = self._editable_data(old)
        data["render"] = self._current_preset()
        T.save_user_theme(name, data)
        if rename and name != old:
            T.delete_user_theme(old)
        self.ctx.cfg.data["theme"] = {}
        self._undo = None
        self.ctx.state.theme = name
        self.ctx.cfg.update({"ui": {"theme": name}})
        apply_settings(self.ctx.state, self.ctx.cfg, data["render"])
        self.ctx.cfg.save()
        self.ctx.state.set_info(f"Saved preset: {name}")
        self._refresh_style()

    def _save_preset(self):
        # Bundled themes stay intact. Explicit save-as asks for a useful name.
        if T.resolve_theme(self._current()).get("builtin"):
            self._duplicate()
        else:
            self._save_as(self._current(), overwrite=True)

    def _duplicate(self):
        ask_text(self.ctx, "Save preset", "Name for this map style", "",
                 self._save_as)

    def _rename(self):
        ask_text(self.ctx, "Rename preset", "New name", self._current(),
                 lambda name: self._save_as(name, rename=True))

    def _make_apply(self, name):
        def apply():
            self.ctx.cfg.data["theme"] = {}
            self._undo = None
            self.ctx.state.theme = name
            self.ctx.cfg.update({"ui": {"theme": name}})
            if self.ctx.on_theme_changed:
                self.ctx.on_theme_changed()
            self.ctx.cfg.save()
            self.ctx.rerender()
        return apply
