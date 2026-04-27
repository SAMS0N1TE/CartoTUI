"""Prompt-toolkit style dictionaries for CartoTUI themes.

Themes drive two surfaces:

  * The terminal **chrome** (titlebar, statusbar, sidebar, compass, dialogs)
    via prompt_toolkit's class-based style system. ``make_style`` returns
    a Style for the configured theme.
  * The map **vector rasteriser**, which draws in real RGB and gets a
    ``VectorStyle`` from ``theme_vector_style``. The rasteriser's output
    then gets tinted at the terminal layer through ``map.*`` classes.

Each theme is just a dict of class → style spec. New widgets pick up theme
support automatically as long as they reference the standard class names.

User overrides land at config-load time: anything under ``cfg["theme"]``
is shallow-merged into the chosen theme's chrome dict, and anything under
``cfg["theme"]["road_colors"]`` overrides the road brightness ramp.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from prompt_toolkit.styles import Style

from cartotui.config import Config

__all__ = [
    "make_style", "border_chars", "theme_palette", "theme_vector_style",
    "available_themes",
]


_AMBER: Dict[str, str] = {
    "titlebar":      "bg:#1a0f00 #ffaa33 bold",
    "titlebar.dim":  "bg:#1a0f00 #886611",
    "toolbar":       "bg:#0f0f0f #ffaa33",
    "toolbar.key":   "bg:#0f0f0f #ffdd66 bold",
    "toolbar.dim":   "bg:#0f0f0f #553300",
    "statusbar":     "bg:#0f0f0f #ffaa33",
    "statusbar.warn": "bg:#0f0f0f #ff5555 bold",
    "statusbar.dim": "bg:#0f0f0f #553300",
    "compass":       "bg:#0f0f0f #ffcc66 bold",
    "crosshair":     "bg:#0f0f0f #ffcc66 bold reverse bold",
    "compass.label": "bg:#0f0f0f #886611",
    "help":          "bg:#1a0f00 #ffcc66",
    "help.title":    "bg:#1a0f00 #ffaa33 bold reverse",
    "help.key":      "bg:#1a0f00 #ffdd66 bold",
    "help.text":     "bg:#1a0f00 #ffcc66",
    "border":        "bg:#0f0f0f #ffaa33",
    "frame.border":  "bg:#0f0f0f #ffaa33",
    "button":        "bg:#332200 #ffaa33",
    "button.focused": "bg:#ffaa33 #1a0f00 bold",
    "dialog":        "bg:#1a0f00 #ffcc66",
    "dialog.body":   "bg:#1a0f00 #ffcc66",
    "sidebar":             "bg:#0a0500 #ffaa33",
    "sidebar.title":       "bg:#1a0f00 #ffdd66 bold",
    "sidebar.tab":         "bg:#1a0f00 #886611",
    "sidebar.tab.active":  "bg:#ffaa33 #1a0f00 bold",
    "sidebar.section":     "bg:#0a0500 #ffdd66 bold",
    "sidebar.label":       "bg:#0a0500 #886611",
    "sidebar.value":       "bg:#0a0500 #ffcc66",
    "sidebar.dim":         "bg:#0a0500 #553300",
    "sidebar.warn":        "bg:#0a0500 #ff5555 bold",
    "sidebar.ok":          "bg:#0a0500 #88ff88 bold",
    "sidebar.aircraft":          "bg:#0a0500 #ffcc66",
    "sidebar.aircraft.selected": "bg:#332200 #ffffff bold",
    "sidebar.input":       "bg:#1a0f00 #ffffff",
    "sidebar.input.focus": "bg:#332200 #ffffff bold",
    "sidebar.hotkey":      "bg:#0a0500 #ffdd66 bold",
    "map":           "bg:#0a0500 #ffaa33",
    "map.water":     "bg:#0a0500 #553311",
    "map.road":      "bg:#0a0500 #ffdd66",
    "map.label":     "bg:#0a0500 #ffffaa bold",
}

_GREEN: Dict[str, str] = {
    "titlebar":      "bg:#001100 #66ff66 bold",
    "titlebar.dim":  "bg:#001100 #226622",
    "toolbar":       "bg:#000a00 #66ff66",
    "toolbar.key":   "bg:#000a00 #aaffaa bold",
    "toolbar.dim":   "bg:#000a00 #114411",
    "statusbar":     "bg:#000a00 #66ff66",
    "statusbar.warn": "bg:#000a00 #ff5555 bold",
    "statusbar.dim": "bg:#000a00 #114411",
    "compass":       "bg:#000a00 #aaffaa bold",
    "crosshair":     "bg:#000a00 #aaffaa bold reverse bold",
    "compass.label": "bg:#000a00 #226622",
    "help":          "bg:#001100 #aaffaa",
    "help.title":    "bg:#001100 #66ff66 bold reverse",
    "help.key":      "bg:#001100 #aaffaa bold",
    "help.text":     "bg:#001100 #88ee88",
    "border":        "bg:#000a00 #66ff66",
    "frame.border":  "bg:#000a00 #66ff66",
    "button":        "bg:#002200 #66ff66",
    "button.focused": "bg:#66ff66 #001100 bold",
    "dialog":        "bg:#001100 #aaffaa",
    "dialog.body":   "bg:#001100 #aaffaa",
    "sidebar":             "bg:#000500 #66ff66",
    "sidebar.title":       "bg:#001100 #aaffaa bold",
    "sidebar.tab":         "bg:#001100 #226622",
    "sidebar.tab.active":  "bg:#66ff66 #001100 bold",
    "sidebar.section":     "bg:#000500 #aaffaa bold",
    "sidebar.label":       "bg:#000500 #226622",
    "sidebar.value":       "bg:#000500 #88ee88",
    "sidebar.dim":         "bg:#000500 #114411",
    "sidebar.warn":        "bg:#000500 #ff5555 bold",
    "sidebar.ok":          "bg:#000500 #aaffaa bold",
    "sidebar.aircraft":          "bg:#000500 #88ee88",
    "sidebar.aircraft.selected": "bg:#002200 #ffffff bold",
    "sidebar.input":       "bg:#001100 #ffffff",
    "sidebar.input.focus": "bg:#002200 #ffffff bold",
    "sidebar.hotkey":      "bg:#000500 #aaffaa bold",
    "map":           "bg:#000500 #66ff66",
    "map.water":     "bg:#000500 #114411",
    "map.road":      "bg:#000500 #aaffaa",
    "map.label":     "bg:#000500 #ddffdd bold",
}

_PAPER: Dict[str, str] = {
    "titlebar":      "bg:#dddddd #000000 bold",
    "titlebar.dim":  "bg:#dddddd #555555",
    "toolbar":       "bg:#eeeeee #000000",
    "toolbar.key":   "bg:#eeeeee #006600 bold",
    "toolbar.dim":   "bg:#eeeeee #888888",
    "statusbar":     "bg:#eeeeee #000000",
    "statusbar.warn": "bg:#eeeeee #aa0000 bold",
    "statusbar.dim": "bg:#eeeeee #888888",
    "compass":       "bg:#eeeeee #003388 bold",
    "crosshair":     "bg:#eeeeee #003388 bold reverse bold",
    "compass.label": "bg:#eeeeee #555555",
    "help":          "bg:#f5f5f5 #000000",
    "help.title":    "bg:#f5f5f5 #003388 bold",
    "help.key":      "bg:#f5f5f5 #006600 bold",
    "help.text":     "bg:#f5f5f5 #000000",
    "border":        "bg:#eeeeee #555555",
    "frame.border":  "bg:#eeeeee #555555",
    "button":        "bg:#cccccc #000000",
    "button.focused": "bg:#003388 #ffffff bold",
    "dialog":        "bg:#f5f5f5 #000000",
    "sidebar":             "bg:#f5f0e0 #000000",
    "sidebar.title":       "bg:#dddddd #000000 bold",
    "sidebar.tab":         "bg:#dddddd #555555",
    "sidebar.tab.active":  "bg:#003388 #ffffff bold",
    "sidebar.section":     "bg:#f5f0e0 #003388 bold",
    "sidebar.label":       "bg:#f5f0e0 #555555",
    "sidebar.value":       "bg:#f5f0e0 #000000",
    "sidebar.dim":         "bg:#f5f0e0 #aaaaaa",
    "sidebar.warn":        "bg:#f5f0e0 #aa0000 bold",
    "sidebar.ok":          "bg:#f5f0e0 #006600 bold",
    "sidebar.aircraft":          "bg:#f5f0e0 #003388",
    "sidebar.aircraft.selected": "bg:#003388 #ffffff bold",
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#ddeeff #000000 bold",
    "sidebar.hotkey":      "bg:#f5f0e0 #006600 bold",
    "map":           "bg:#f5f0e0 #000000",
    "map.water":     "bg:#f5f0e0 #88aabb",
    "map.road":      "bg:#f5f0e0 #221100",
    "map.label":     "bg:#f5f0e0 #000000 bold",
}


_RETRO: Dict[str, str] = {
    "titlebar":      "bg:#1a0f00 #ffaa33 bold",
    "titlebar.dim":  "bg:#1a0f00 #886611",
    "toolbar":       "bg:#0f0f0f #ffaa33",
    "toolbar.key":   "bg:#0f0f0f #66ff66 bold",
    "toolbar.dim":   "bg:#0f0f0f #555555",
    "statusbar":     "bg:#0f0f0f #88ff88",
    "statusbar.warn": "bg:#0f0f0f #ff5555 bold",
    "statusbar.dim": "bg:#0f0f0f #555555",
    "compass":       "bg:#0f0f0f #ffaa33 bold",
    "map":           "bg:#0f0f0f #ffaa33",
    "crosshair":     "bg:#0f0f0f #ffaa33 bold reverse bold",
    "compass.label": "bg:#0f0f0f #886611",
    "help":          "bg:#1a0f00 #ffcc66",
    "help.title":    "bg:#1a0f00 #ffaa33 bold reverse",
    "help.key":      "bg:#1a0f00 #66ff66 bold",
    "help.text":     "bg:#1a0f00 #ffcc66",
    "border":        "bg:#0f0f0f #ffaa33",
    "frame.border":  "bg:#0f0f0f #ffaa33",
    "button":        "bg:#332200 #ffaa33",
    "button.focused": "bg:#ffaa33 #1a0f00 bold",
    "dialog":        "bg:#1a0f00 #ffcc66",
    "dialog.body":   "bg:#1a0f00 #ffcc66",
    "dialog.shadow": "bg:#000000",
    "scrollbar.background": "bg:#1a0f00",
    "scrollbar.button":     "bg:#ffaa33",
    "sidebar":             "bg:#0f0f0f #ffaa33",
    "sidebar.title":       "bg:#1a0f00 #ffaa33 bold",
    "sidebar.tab":         "bg:#1a0f00 #886611",
    "sidebar.tab.active":  "bg:#66ff66 #0f0f0f bold",
    "sidebar.section":     "bg:#0f0f0f #66ff66 bold",
    "sidebar.label":       "bg:#0f0f0f #886611",
    "sidebar.value":       "bg:#0f0f0f #ffcc66",
    "sidebar.dim":         "bg:#0f0f0f #555555",
    "sidebar.warn":        "bg:#0f0f0f #ff5555 bold",
    "sidebar.ok":          "bg:#0f0f0f #88ff88 bold",
    "sidebar.aircraft":          "bg:#0f0f0f #ffcc66",
    "sidebar.aircraft.selected": "bg:#332200 #ffffff bold",
    "sidebar.input":       "bg:#1a0f00 #ffffff",
    "sidebar.input.focus": "bg:#332200 #ffffff bold",
    "sidebar.hotkey":      "bg:#0f0f0f #66ff66 bold",
}

_DARK: Dict[str, str] = {
    "titlebar":      "bg:#1f2430 #c0caf5 bold",
    "titlebar.dim":  "bg:#1f2430 #565f89",
    "toolbar":       "bg:#16161e #c0caf5",
    "toolbar.key":   "bg:#16161e #9ece6a bold",
    "toolbar.dim":   "bg:#16161e #565f89",
    "statusbar":     "bg:#16161e #c0caf5",
    "statusbar.warn": "bg:#16161e #f7768e bold",
    "statusbar.dim": "bg:#16161e #565f89",
    "compass":       "bg:#16161e #7aa2f7 bold",
    "map":           "bg:#16161e #7aa2f7",
    "crosshair":     "bg:#16161e #7aa2f7 bold reverse bold",
    "compass.label": "bg:#16161e #565f89",
    "help":          "bg:#1f2430 #c0caf5",
    "help.title":    "bg:#1f2430 #7aa2f7 bold",
    "help.key":      "bg:#1f2430 #9ece6a bold",
    "help.text":     "bg:#1f2430 #c0caf5",
    "border":        "bg:#16161e #565f89",
    "frame.border":  "bg:#16161e #565f89",
    "button":        "bg:#292e42 #c0caf5",
    "button.focused": "bg:#7aa2f7 #1a1b26 bold",
    "dialog":        "bg:#1f2430 #c0caf5",
    "dialog.body":   "bg:#1f2430 #c0caf5",
    "dialog.shadow": "bg:#000000",
    "sidebar":             "bg:#1a1b26 #c0caf5",
    "sidebar.title":       "bg:#1f2430 #7aa2f7 bold",
    "sidebar.tab":         "bg:#1f2430 #565f89",
    "sidebar.tab.active":  "bg:#7aa2f7 #1a1b26 bold",
    "sidebar.section":     "bg:#1a1b26 #7aa2f7 bold",
    "sidebar.label":       "bg:#1a1b26 #565f89",
    "sidebar.value":       "bg:#1a1b26 #c0caf5",
    "sidebar.dim":         "bg:#1a1b26 #414868",
    "sidebar.warn":        "bg:#1a1b26 #f7768e bold",
    "sidebar.ok":          "bg:#1a1b26 #9ece6a bold",
    "sidebar.aircraft":          "bg:#1a1b26 #c0caf5",
    "sidebar.aircraft.selected": "bg:#292e42 #ffffff bold",
    "sidebar.input":       "bg:#1f2430 #ffffff",
    "sidebar.input.focus": "bg:#292e42 #ffffff bold",
    "sidebar.hotkey":      "bg:#1a1b26 #9ece6a bold",
}

_LIGHT: Dict[str, str] = {
    "titlebar":      "bg:#dddddd #000000 bold",
    "titlebar.dim":  "bg:#dddddd #555555",
    "toolbar":       "bg:#eeeeee #000000",
    "toolbar.key":   "bg:#eeeeee #006600 bold",
    "toolbar.dim":   "bg:#eeeeee #555555",
    "statusbar":     "bg:#eeeeee #000000",
    "statusbar.warn": "bg:#eeeeee #aa0000 bold",
    "statusbar.dim": "bg:#eeeeee #555555",
    "compass":       "bg:#eeeeee #003388 bold",
    "map":           "bg:#eeeeee #003388",
    "crosshair":     "bg:#eeeeee #003388 bold reverse bold",
    "compass.label": "bg:#eeeeee #555555",
    "help":          "bg:#f5f5f5 #000000",
    "help.title":    "bg:#f5f5f5 #003388 bold",
    "help.key":      "bg:#f5f5f5 #006600 bold",
    "help.text":     "bg:#f5f5f5 #000000",
    "border":        "bg:#eeeeee #555555",
    "frame.border":  "bg:#eeeeee #555555",
    "button":        "bg:#cccccc #000000",
    "button.focused": "bg:#003388 #ffffff bold",
    "dialog":        "bg:#f5f5f5 #000000",
    "sidebar":             "bg:#f0f0f0 #000000",
    "sidebar.title":       "bg:#dddddd #000000 bold",
    "sidebar.tab":         "bg:#dddddd #555555",
    "sidebar.tab.active":  "bg:#003388 #ffffff bold",
    "sidebar.section":     "bg:#f0f0f0 #003388 bold",
    "sidebar.label":       "bg:#f0f0f0 #555555",
    "sidebar.value":       "bg:#f0f0f0 #000000",
    "sidebar.dim":         "bg:#f0f0f0 #aaaaaa",
    "sidebar.warn":        "bg:#f0f0f0 #aa0000 bold",
    "sidebar.ok":          "bg:#f0f0f0 #006600 bold",
    "sidebar.aircraft":          "bg:#f0f0f0 #003388",
    "sidebar.aircraft.selected": "bg:#003388 #ffffff bold",
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#ddeeff #000000 bold",
    "sidebar.hotkey":      "bg:#f0f0f0 #006600 bold",
}


_THEMES: Dict[str, Dict[str, str]] = {
    "amber": _AMBER,
    "green": _GREEN,
    "paper": _PAPER,
    "retro": _RETRO,
    "dark":  _DARK,
    "light": _LIGHT,
}


_BORDERS = {
    "ascii":   {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+", "x": "+"},
    "heavy":   {"h": "━", "v": "┃", "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "x": "╋"},
    "rounded": {"h": "─", "v": "│", "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "x": "┼"},
}


def border_chars(style: str) -> dict:
    return _BORDERS.get(style, _BORDERS["heavy"])


def available_themes() -> Tuple[str, ...]:
    return tuple(_THEMES.keys())


def make_style(cfg: Config) -> Style:
    theme_name = cfg["ui"].get("theme", "amber")
    base = dict(_THEMES.get(theme_name, _AMBER))
    # Optional user overrides at cfg["theme"]["chrome"] — flat dict of
    # class-name → spec; we merge in.
    try:
        overrides = cfg.data.get("theme", {}).get("chrome", {})
    except Exception:
        overrides = {}
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if isinstance(k, str) and isinstance(v, str):
                base[k] = v
    return Style.from_dict(base)


def theme_palette(theme: str) -> dict:
    """Return the colour dict for a theme — used by chrome that needs raw RGB
    (e.g. the map renderer can pick a complementary tint)."""
    return _THEMES.get(theme, _AMBER)


def theme_vector_style(
    theme: str,
    user_overrides: Optional[Dict] = None,
):
    """Return a ``raster_vector.VectorStyle`` for the named theme.

    Imports lazily so this module doesn't drag in Pillow at import time
    (themes is loaded by ``cli --print-config`` etc.).

    User overrides at ``cfg["theme"]["road_colors"]`` shape::

        {"road_colors": {"motorway": [255, 240, 100], ...}}

    Both class names (motorway, primary, ...) and numeric priorities
    (10, 8, ...) are accepted.
    """
    from cartotui.raster_vector import (
        ROAD_CLASS_PRIORITY, default_style,
    )

    style = default_style(theme)

    if not user_overrides:
        return style

    # road_colors override — priority dict copy, then mutate
    rc = dict(style.road_colors)
    raw = user_overrides.get("road_colors") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                if isinstance(k, str):
                    pri = ROAD_CLASS_PRIORITY.get(k.lower())
                else:
                    pri = int(k)
                if pri is None:
                    continue
                if isinstance(v, (list, tuple)) and len(v) == 3:
                    rc[pri] = (int(v[0]), int(v[1]), int(v[2]))
            except (TypeError, ValueError):
                continue
    style.road_colors = rc

    # Optional scalar overrides for water/park/building/aircraft
    for key, attr in (
        ("water", "water"),
        ("park", "park"),
        ("building", "building"),
        ("bg", "bg"),
        ("aircraft", "aircraft_color"),
        ("aircraft_selected", "aircraft_selected_color"),
        ("aircraft_emergency", "aircraft_emergency_color"),
        ("aircraft_label", "aircraft_label_color"),
    ):
        v = user_overrides.get(key)
        if isinstance(v, (list, tuple)) and len(v) == 3:
            try:
                setattr(style, attr, (int(v[0]), int(v[1]), int(v[2])))
            except (TypeError, ValueError):
                pass

    return style
