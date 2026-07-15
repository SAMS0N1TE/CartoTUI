from __future__ import annotations

import json
import os
import platform
import threading
from typing import Dict, Optional, Tuple

__all__ = [
    "available_theme_names", "resolve_theme", "chrome_style_map",
    "vector_style_kwargs", "theme_border_pref", "reload_themes",
    "user_theme_dir", "builtin_theme_dir", "save_user_theme",
    "delete_user_theme", "theme_source_path", "CHROME_CLASSES",
    "UI_KEYS", "MAP_KEYS",
]

_BUILTIN_ORDER = [
    "amber", "green", "paper", "retro", "dark",
    "light", "hicon", "ega", "win31", "night",
]

UI_KEYS = [
    "bg", "fg", "dim", "border", "accent", "key", "section",
    "warn", "ok", "panel_bg", "title_bg", "title_fg",
    "sel_bg", "sel_fg", "input_bg", "input_fg",
    "input_focus_bg", "input_focus_fg", "btn_bg",
]

MAP_KEYS = [
    "bg", "water", "park", "building", "road", "label", "halo",
    "aircraft", "aircraft_selected", "aircraft_emergency",
    "aircraft_label", "aircraft_halo",
]

_ROAD_CLASS_PRIORITY = {
    "highway": 10, "motorway": 10, "trunk": 9, "primary": 8,
    "secondary": 7, "tertiary": 6, "minor_road": 5, "residential": 4,
    "street": 4, "service": 3, "path": 2, "footway": 2, "cycleway": 2,
    "track": 2, "other": 1,
}

_lock = threading.RLock()
_cache: Optional[Dict[str, dict]] = None

def builtin_theme_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")

def _config_home() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, "CartoTUI")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "CartoTUI")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "cartotui")

def user_theme_dir() -> str:
    return os.path.join(_config_home(), "themes")

def _hex_to_rgb(s: str) -> Tuple[int, int, int]:
    s = str(s).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return (128, 128, 128)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (128, 128, 128)

def _rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"

def _shade(hexstr: str, pct: float) -> str:
    r, g, b = _hex_to_rgb(hexstr)
    if pct >= 0:
        f = pct / 100.0
        r = r + (255 - r) * f
        g = g + (255 - g) * f
        b = b + (255 - b) * f
    else:
        f = 1.0 + pct / 100.0
        r *= f
        g *= f
        b *= f
    return _rgb_to_hex((r, g, b))

def _blend(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex((ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t))

def _lum(hexstr: str) -> float:
    r, g, b = _hex_to_rgb(hexstr)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b)

def _derive_ui(ui: dict) -> dict:
    u = dict(ui or {})
    bg = u.get("bg", "#101014")
    fg = u.get("fg", "#c8c8c8")
    dark = _lum(bg) < 128

    def d(key, val):
        return u.get(key, val)

    dim = d("dim", _blend(fg, bg, 0.5))
    out = {
        "bg": bg,
        "fg": fg,
        "dim": dim,
        "border": d("border", _blend(dim, bg, 0.35)),
        "accent": d("accent", _shade(fg, 25) if dark else _shade(fg, -25)),
        "warn": d("warn", "#ff5555"),
        "ok": d("ok", "#66cc66"),
        "panel_bg": d("panel_bg", _shade(bg, 9) if dark else _shade(bg, -5)),
        "title_bg": d("title_bg", _shade(bg, 20) if dark else _shade(bg, -12)),
        "title_fg": d("title_fg", fg),
    }
    out["key"] = d("key", out["accent"])
    out["section"] = d("section", out["accent"])
    out["sel_bg"] = d("sel_bg", out["accent"])
    out["sel_fg"] = d("sel_fg", bg)
    out["btn_bg"] = d("btn_bg", _shade(out["panel_bg"], 14) if dark else _shade(out["panel_bg"], -8))
    out["input_bg"] = d("input_bg", _shade(out["panel_bg"], 12) if dark else "#ffffff")
    out["input_fg"] = d("input_fg", fg if dark else "#000000")
    out["input_focus_bg"] = d("input_focus_bg", out["sel_bg"])
    out["input_focus_fg"] = d("input_focus_fg", out["sel_fg"])
    return out

def _s(bg: str, fg: str, extra: str = "") -> str:
    e = (" " + extra) if extra else ""
    return f"bg:{bg} {fg}{e}"

CHROME_CLASSES = [
    "titlebar", "titlebar.dim", "titlebar.hotkey", "toolbar", "toolbar.key", "toolbar.dim",
    "statusbar", "statusbar.warn", "statusbar.dim", "compass", "compass.label",
    "crosshair", "help", "help.title", "help.key", "help.text", "border",
    "frame.border", "button", "button.focused", "dialog", "dialog.body",
    "dialog.shadow", "sidebar", "sidebar.title", "sidebar.tab",
    "sidebar.tab.active", "sidebar.section", "sidebar.label", "sidebar.value",
    "sidebar.dim", "sidebar.warn", "sidebar.ok", "sidebar.aircraft",
    "sidebar.aircraft.selected", "sidebar.input", "sidebar.input.focus",
    "sidebar.hotkey", "map", "map.water", "map.road", "map.label",
    "panel", "panel.border", "panel.title", "panel.title.active",
    "panel.button", "panel.section", "panel.label", "panel.value",
    "panel.dim", "panel.warn", "panel.ok", "panel.hotkey",
]

def _gen_chrome(u: dict, map_bg: Optional[str] = None) -> Dict[str, str]:
    """Build the chrome style map.

    ``map_bg`` is the theme's rasterised map background. The renderer emits
    fg-only styles, so a cell of uniform map background is a plain space and
    the *cell* background shows through. That cell background has to be the
    map's own bg, not the UI's, or themes whose chrome differs from their map
    (win31: grey chrome, navy map) show bare chrome wherever the map is flat.
    """
    bg = u["bg"]; fg = u["fg"]; dim = u["dim"]; border = u["border"]
    accent = u["accent"]; key = u["key"]; section = u["section"]
    warn = u["warn"]; ok = u["ok"]; panel_bg = u["panel_bg"]
    title_bg = u["title_bg"]; title_fg = u["title_fg"]
    sel_bg = u["sel_bg"]; sel_fg = u["sel_fg"]; btn_bg = u["btn_bg"]
    input_bg = u["input_bg"]; input_fg = u["input_fg"]
    ifb = u["input_focus_bg"]; iff = u["input_focus_fg"]
    mbg = map_bg or bg
    return {
        "titlebar": _s(title_bg, title_fg, "bold"),
        "titlebar.dim": _s(title_bg, dim),
        "titlebar.hotkey": _s(title_bg, key, "bold"),
        "toolbar": _s(bg, fg),
        "toolbar.key": _s(bg, key, "bold"),
        "toolbar.dim": _s(bg, dim),
        "statusbar": _s(bg, fg),
        "statusbar.warn": _s(bg, warn, "bold"),
        "statusbar.dim": _s(bg, dim),
        "compass": _s(bg, accent, "bold"),
        "compass.label": _s(bg, dim),
        "crosshair": _s(bg, accent, "bold reverse"),
        "help": _s(panel_bg, fg),
        "help.title": _s(panel_bg, accent, "bold"),
        "help.key": _s(panel_bg, key, "bold"),
        "help.text": _s(panel_bg, fg),
        "border": _s(bg, border),
        "frame.border": _s(bg, border),
        "button": _s(btn_bg, fg),
        "button.focused": _s(sel_bg, sel_fg, "bold"),
        "dialog": _s(panel_bg, fg),
        "dialog.body": _s(panel_bg, fg),
        "dialog.shadow": f"bg:{_shade(bg, -45)}",
        "sidebar": _s(panel_bg, fg),
        "sidebar.title": _s(title_bg, title_fg, "bold"),
        "sidebar.tab": _s(panel_bg, dim),
        "sidebar.tab.active": _s(sel_bg, sel_fg, "bold"),
        "sidebar.section": _s(panel_bg, section, "bold"),
        "sidebar.label": _s(panel_bg, dim),
        "sidebar.value": _s(panel_bg, fg),
        "sidebar.dim": _s(panel_bg, border),
        "sidebar.warn": _s(panel_bg, warn, "bold"),
        "sidebar.ok": _s(panel_bg, ok, "bold"),
        "sidebar.aircraft": _s(panel_bg, fg),
        "sidebar.aircraft.selected": _s(sel_bg, sel_fg, "bold"),
        "sidebar.input": _s(input_bg, input_fg),
        "sidebar.input.focus": _s(ifb, iff, "bold"),
        "sidebar.hotkey": _s(panel_bg, key),
        "map": _s(mbg, fg),
        "map.water": _s(mbg, dim),
        "map.road": _s(mbg, fg),
        "map.label": _s(mbg, accent),
        "panel": _s(panel_bg, fg),
        "panel.border": _s(panel_bg, border),
        "panel.title": _s(title_bg, title_fg, "bold"),
        "panel.title.active": _s(sel_bg, sel_fg, "bold"),
        "panel.button": _s(btn_bg, accent, "bold"),
        "panel.section": _s(panel_bg, section, "bold"),
        "panel.label": _s(panel_bg, dim),
        "panel.value": _s(panel_bg, fg),
        "panel.dim": _s(panel_bg, border),
        "panel.warn": _s(panel_bg, warn, "bold"),
        "panel.ok": _s(panel_bg, ok, "bold"),
        "panel.hotkey": _s(panel_bg, key),
    }

def _read_dir(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not os.path.isdir(path):
        return out
    for fn in sorted(os.listdir(path)):
        if not fn.lower().endswith(".json"):
            continue
        full = os.path.join(path, fn)
        try:
            with open(full, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        name = str(data.get("name") or os.path.splitext(fn)[0]).strip().lower()
        if not name:
            continue
        data["name"] = name
        data["_path"] = full
        data["_builtin"] = os.path.normpath(path) == os.path.normpath(builtin_theme_dir())
        out[name] = data
    return out

def _load_all() -> Dict[str, dict]:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        merged: Dict[str, dict] = {}
        merged.update(_read_dir(builtin_theme_dir()))
        merged.update(_read_dir(user_theme_dir()))
        _cache = merged
        return merged

def reload_themes() -> None:
    global _cache
    with _lock:
        _cache = None

def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _resolve_raw(name: str, seen: Optional[set] = None) -> dict:
    themes = _load_all()
    seen = seen or set()
    raw = themes.get(name)
    if raw is None:
        raw = themes.get("amber") or {}
    parent = raw.get("extends")
    if parent and parent not in seen and parent in themes:
        seen.add(parent)
        base = _resolve_raw(parent, seen)
        return _deep_merge(base, {k: v for k, v in raw.items()
                                  if k not in ("extends", "_path", "_builtin")})
    return dict(raw)

def available_theme_names() -> Tuple[str, ...]:
    themes = _load_all()
    ordered = [n for n in _BUILTIN_ORDER if n in themes]
    extra = sorted(n for n in themes if n not in _BUILTIN_ORDER)
    return tuple(ordered + extra)

def resolve_theme(name: str) -> dict:
    raw = _resolve_raw(str(name).lower())
    ui = _derive_ui(raw.get("ui", {}))
    return {
        "name": raw.get("name", name),
        "ui": ui,
        "map": raw.get("map", {}),
        "chrome_overrides": raw.get("chrome", {}) if isinstance(raw.get("chrome"), dict) else {},
        "border": raw.get("border", "auto"),
        "builtin": bool(raw.get("_builtin", False)),
        "path": raw.get("_path"),
    }

def chrome_style_map(name: str, extra_overrides: Optional[dict] = None) -> Dict[str, str]:
    t = resolve_theme(name)
    base = _gen_chrome(t["ui"], (t["map"] or {}).get("bg"))
    for k, v in t["chrome_overrides"].items():
        if isinstance(k, str) and isinstance(v, str):
            base[k] = v
    if extra_overrides:
        for k, v in extra_overrides.items():
            if isinstance(k, str) and isinstance(v, str):
                base[k] = v
    return base

def vector_style_kwargs(name: str) -> dict:
    t = resolve_theme(name)
    m = t["map"] or {}
    ui = t["ui"]
    bg = m.get("bg", ui["bg"])
    road = m.get("road", ui["fg"])

    def rgb(key, default):
        return _hex_to_rgb(m.get(key, default))

    road_colors: Dict[int, Tuple[int, int, int]] = {}
    for p in range(1, 11):
        t_mix = 0.72 * ((10 - p) / 9.0)
        road_colors[p] = _hex_to_rgb(_blend(road, bg, t_mix))
    roads = m.get("roads", {})
    if isinstance(roads, dict):
        for cls, hexv in roads.items():
            try:
                if isinstance(cls, str) and cls.lower() in _ROAD_CLASS_PRIORITY:
                    pri = _ROAD_CLASS_PRIORITY[cls.lower()]
                else:
                    pri = int(cls)
                if 1 <= pri <= 10:
                    road_colors[pri] = _hex_to_rgb(hexv)
            except (TypeError, ValueError):
                continue

    return {
        "bg": _hex_to_rgb(bg),
        "water": rgb("water", "#5f6978"),
        "park": rgb("park", "#3c503c"),
        "building": rgb("building", "#4b4b50"),
        "road_color": _hex_to_rgb(road),
        "label_color": rgb("label", ui["accent"]),
        "halo_color": rgb("halo", "#000000" if _lum(bg) < 128 else "#ffffff"),
        "aircraft_color": rgb("aircraft", "#ffc83c"),
        "aircraft_selected_color": rgb("aircraft_selected", "#ffffff"),
        "aircraft_emergency_color": rgb("aircraft_emergency", "#ff5050"),
        "aircraft_label_color": rgb("aircraft_label", m.get("label", ui["accent"])),
        "aircraft_halo_color": rgb("aircraft_halo", "#000000" if _lum(bg) < 128 else "#ffffff"),
        "road_colors": road_colors,
        "draw_labels": bool(m.get("draw_labels", False)),
    }

def theme_border_pref(name: str) -> str:
    return str(resolve_theme(name).get("border", "auto"))

def theme_render(name: str) -> dict:
    raw = _resolve_raw(str(name).lower())
    r = raw.get("render")
    return dict(r) if isinstance(r, dict) else {}

def theme_source_path(name: str) -> Optional[str]:
    return resolve_theme(name).get("path")

def save_user_theme(name: str, data: dict) -> str:
    d = user_theme_dir()
    os.makedirs(d, exist_ok=True)
    name = str(name).strip().lower().replace(" ", "_")
    data = dict(data)
    data["name"] = name
    for k in ("_path", "_builtin"):
        data.pop(k, None)
    path = os.path.join(d, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    reload_themes()
    return path

def delete_user_theme(name: str) -> bool:
    path = os.path.join(user_theme_dir(), str(name).lower() + ".json")
    if os.path.exists(path):
        try:
            os.remove(path)
            reload_themes()
            return True
        except OSError:
            return False
    return False
