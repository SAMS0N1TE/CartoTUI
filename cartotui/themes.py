
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from prompt_toolkit.styles import Style

from cartotui import theme_loader
from cartotui.config import Config

__all__ = [
    "make_style", "border_chars", "theme_palette", "theme_vector_style",
    "available_themes",
    "group_box_top", "group_box_bottom", "kv_row", "tab_strip_rows",
]

_BORDERS = {
    "ascii":   {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+", "x": "+",
                "th": "-", "tv": "|",
                "tab_tl": "+", "tab_tr": "+", "tab_sep": "+"},
    "heavy":   {"h": "━", "v": "┃", "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "x": "╋",
                "th": "─", "tv": "│",
                "tab_tl": "┌", "tab_tr": "┐", "tab_sep": "┬"},
    "rounded": {"h": "─", "v": "│", "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "x": "┼",
                "th": "─", "tv": "│",
                "tab_tl": "╭", "tab_tr": "╮", "tab_sep": "┬"},
}

def border_chars(style: str, theme: Optional[str] = None) -> dict:
    if theme is not None:
        pref = theme_loader.theme_border_pref(theme)
        if pref in _BORDERS:
            return _BORDERS[pref]
    return _BORDERS.get(style, _BORDERS["heavy"])

def group_box_top(title: str, w: int, bc: Optional[dict] = None) -> str:
    if bc is None:
        bc = _BORDERS["heavy"]
    tl = bc["tl"]
    tr = bc["tr"]
    h = bc["h"]
    prefix = tl + h + " " + title + " "
    suffix = tr
    pad = max(0, w - len(prefix) - len(suffix))
    return prefix + h * pad + suffix

def group_box_bottom(w: int, bc: Optional[dict] = None) -> str:
    if bc is None:
        bc = _BORDERS["heavy"]
    bl = bc["bl"]
    br = bc["br"]
    h = bc["h"]
    inner = max(0, w - 2)
    return bl + h * inner + br

def kv_row(label: str, value: str, hot: Optional[str], w: int,
           bc: Optional[dict] = None) -> str:
    if bc is None:
        bc = _BORDERS["heavy"]
    v = bc["v"]
    label_part = " " + label + ":"
    hot_part = f" [{hot}]" if hot else ""
    inner = w - 2
    val_w = inner - len(label_part) - len(hot_part) - 1
    if val_w < 1:
        val_w = 1
    val = str(value)
    if len(val) > val_w:
        val = val[:val_w - 1] + "…"
    val = val.rjust(val_w)
    row = v + label_part + " " + val + hot_part + " " + v
    if len(row) < w:
        row = row[:-1] + " " * (w - len(row)) + v
    elif len(row) > w:
        row = row[:w - 1] + v
    return row

def tab_strip_rows(
    tabs: Tuple[str, ...],
    active: int,
    w: int,
    bc: Optional[dict] = None,
) -> Tuple[str, str]:
    if bc is None:
        bc = _BORDERS["ascii"]
    n = len(tabs)
    if n == 0:
        return ("+" + "-" * (w - 2) + "+", "|" + " " * (w - 2) + "|")

    total_inner = w - (n + 1)
    slot_base = max(1, total_inner // n)
    leftover = max(0, total_inner - slot_base * n)

    tl = bc["tab_tl"]
    tr = bc["tab_tr"]
    sep = bc["tab_sep"]
    h = bc["th"]
    v = bc["tv"]

    top_parts = [tl]
    for i in range(n):
        sw = slot_base + (1 if i < leftover else 0)
        top_parts.append(h * sw)
        top_parts.append(sep if i < n - 1 else tr)
    top = "".join(top_parts)

    label_parts = [v]
    for i in range(n):
        sw = slot_base + (1 if i < leftover else 0)
        label = (" " + tabs[i] + " ").ljust(sw)[:sw]
        label_parts.append(label)
        label_parts.append(v)
    labels = "".join(label_parts)

    top = (top + " " * w)[:w]
    labels = (labels + " " * w)[:w]
    return top, labels

def tab_strip_slot_ranges(
    tabs: Tuple[str, ...],
    w: int,
) -> List[Tuple[int, int]]:
    n = len(tabs)
    if n == 0:
        return []
    total_inner = w - (n + 1)
    slot_base = max(1, total_inner // n)
    leftover = max(0, total_inner - slot_base * n)
    ranges = []
    col = 1
    for i in range(n):
        sw = slot_base + (1 if i < leftover else 0)
        ranges.append((col, col + sw))
        col += sw + 1
    return ranges

def available_themes() -> Tuple[str, ...]:
    return theme_loader.available_theme_names()

def make_style(cfg: Config) -> Style:
    theme_name = cfg["ui"].get("theme", "amber")
    try:
        overrides = cfg.data.get("theme", {}).get("chrome", {})
    except Exception:
        overrides = {}
    if not isinstance(overrides, dict):
        overrides = {}
    base = theme_loader.chrome_style_map(theme_name, overrides)
    return Style.from_dict(base)

def theme_palette(theme: str) -> dict:
    return theme_loader.chrome_style_map(theme)

def _coerce_rgb(v) -> Optional[Tuple[int, int, int]]:
    if isinstance(v, str):
        r, g, b = theme_loader._hex_to_rgb(v)
        return (r, g, b)
    if isinstance(v, (list, tuple)) and len(v) == 3:
        try:
            return (int(v[0]), int(v[1]), int(v[2]))
        except (TypeError, ValueError):
            return None
    return None

def apply_road_highlight(style):
    def brighten(rgb, f=1.4):
        return tuple(min(255, int(c * f) + 8) for c in rgb)

    def toward_bg(rgb, t=0.5):
        return tuple(int(rgb[i] + (style.bg[i] - rgb[i]) * t) for i in range(3))

    style.road_widths = {p: min(255, int(w * 1.7) + 1)
                         for p, w in style.road_widths.items()}
    style.road_color = brighten(style.road_color)
    style.road_colors = {p: brighten(c) for p, c in style.road_colors.items()}
    style.water = toward_bg(style.water)
    style.park = toward_bg(style.park)
    style.building = toward_bg(style.building)
    return style

def theme_vector_style(theme: str, user_overrides: Optional[Dict] = None):
    from cartotui.raster_vector import ROAD_CLASS_PRIORITY, VectorStyle

    kwargs = theme_loader.vector_style_kwargs(theme)
    style = VectorStyle(**kwargs)

    if not user_overrides:
        return style

    rc = dict(style.road_colors)
    raw = user_overrides.get("road_colors") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                if isinstance(k, str) and k.lower() in ROAD_CLASS_PRIORITY:
                    pri = ROAD_CLASS_PRIORITY[k.lower()]
                else:
                    pri = int(k)
            except (TypeError, ValueError):
                continue
            rgb = _coerce_rgb(v)
            if rgb is not None and 1 <= pri <= 10:
                rc[pri] = rgb
    style.road_colors = rc

    for key, attr in (
        ("water", "water"),
        ("park", "park"),
        ("building", "building"),
        ("bg", "bg"),
        ("road", "road_color"),
        ("label", "label_color"),
        ("halo", "halo_color"),
        ("aircraft", "aircraft_color"),
        ("aircraft_selected", "aircraft_selected_color"),
        ("aircraft_emergency", "aircraft_emergency_color"),
        ("aircraft_label", "aircraft_label_color"),
    ):
        rgb = _coerce_rgb(user_overrides.get(key))
        if rgb is not None:
            setattr(style, attr, rgb)

    return style
