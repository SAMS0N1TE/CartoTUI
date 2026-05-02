
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from prompt_toolkit.styles import Style

from cartotui.config import Config

__all__ = [
    "make_style", "border_chars", "theme_palette", "theme_vector_style",
    "available_themes",
    "group_box_top", "group_box_bottom", "kv_row", "tab_strip_rows",
]

_AMBER: Dict[str, str] = {
    "titlebar":      "bg:#000000 #e8e8e8",
    "titlebar.dim":  "bg:#000000 #707070",
    "toolbar":       "bg:#000000 #c8c8c8",
    "toolbar.key":   "bg:#000000 #e8e8e8",
    "toolbar.dim":   "bg:#000000 #505050",
    "statusbar":     "bg:#000000 #c8c8c8",
    "statusbar.warn": "bg:#000000 #c8c8c8 reverse",
    "statusbar.dim": "bg:#000000 #505050",
    "compass":       "bg:#000000 #e8e8e8",
    "crosshair":     "bg:#000000 #e8e8e8 reverse",
    "compass.label": "bg:#000000 #707070",
    "help":          "bg:#000000 #c8c8c8",
    "help.title":    "bg:#000000 #e8e8e8 reverse",
    "help.key":      "bg:#000000 #e8e8e8",
    "help.text":     "bg:#000000 #c8c8c8",
    "border":        "bg:#000000 #707070",
    "frame.border":  "bg:#000000 #707070",
    "button":        "bg:#000000 #c8c8c8",
    "button.focused": "bg:#000000 #ffffff reverse",
    "dialog":        "bg:#000000 #c8c8c8",
    "dialog.body":   "bg:#000000 #c8c8c8",
    "sidebar":             "bg:#000000 #c8c8c8",
    "sidebar.title":       "bg:#000000 #c8c8c8",
    "sidebar.tab":         "bg:#000000 #707070",
    "sidebar.tab.active":  "bg:#000000 #e8e8e8 reverse",
    "sidebar.section":     "bg:#000000 #e8e8e8",
    "sidebar.label":       "bg:#000000 #909090",
    "sidebar.value":       "bg:#000000 #c8c8c8",
    "sidebar.dim":         "bg:#000000 #505050",
    "sidebar.warn":        "bg:#000000 #c8c8c8 reverse",
    "sidebar.ok":          "bg:#000000 #e8e8e8",
    "sidebar.aircraft":          "bg:#000000 #c8c8c8",
    "sidebar.aircraft.selected": "bg:#000000 #e8e8e8 reverse",
    "sidebar.input":       "bg:#000000 #e8e8e8 reverse",
    "sidebar.input.focus": "bg:#000000 #ffffff reverse",
    "sidebar.hotkey":      "bg:#000000 #e8e8e8",
    "map":           "bg:#000000 #c8c8c8",
    "map.water":     "bg:#000000 #505050",
    "map.road":      "bg:#000000 #e8e8e8",
    "map.label":     "bg:#000000 #ffffff",
}

_GREEN: Dict[str, str] = {
    "titlebar":      "bg:#000000 #66cc66",
    "titlebar.dim":  "bg:#000000 #336633",
    "toolbar":       "bg:#000000 #44aa44",
    "toolbar.key":   "bg:#000000 #66cc66",
    "toolbar.dim":   "bg:#000000 #2a5a2a",
    "statusbar":     "bg:#000000 #44aa44",
    "statusbar.warn": "bg:#000000 #44aa44 reverse",
    "statusbar.dim": "bg:#000000 #2a5a2a",
    "compass":       "bg:#000000 #66cc66",
    "crosshair":     "bg:#000000 #66cc66 reverse",
    "compass.label": "bg:#000000 #336633",
    "help":          "bg:#000000 #44aa44",
    "help.title":    "bg:#000000 #66cc66 reverse",
    "help.key":      "bg:#000000 #66cc66",
    "help.text":     "bg:#000000 #44aa44",
    "border":        "bg:#000000 #336633",
    "frame.border":  "bg:#000000 #336633",
    "button":        "bg:#000000 #44aa44",
    "button.focused": "bg:#000000 #66cc66 reverse",
    "dialog":        "bg:#000000 #44aa44",
    "dialog.body":   "bg:#000000 #44aa44",
    "sidebar":             "bg:#000000 #44aa44",
    "sidebar.title":       "bg:#000000 #44aa44",
    "sidebar.tab":         "bg:#000000 #2a5a2a",
    "sidebar.tab.active":  "bg:#000000 #66cc66 reverse",
    "sidebar.section":     "bg:#000000 #66cc66",
    "sidebar.label":       "bg:#000000 #336633",
    "sidebar.value":       "bg:#000000 #44aa44",
    "sidebar.dim":         "bg:#000000 #2a5a2a",
    "sidebar.warn":        "bg:#000000 #44aa44 reverse",
    "sidebar.ok":          "bg:#000000 #66cc66",
    "sidebar.aircraft":          "bg:#000000 #44aa44",
    "sidebar.aircraft.selected": "bg:#000000 #66cc66 reverse",
    "sidebar.input":       "bg:#000000 #66cc66 reverse",
    "sidebar.input.focus": "bg:#000000 #88ee88 reverse",
    "sidebar.hotkey":      "bg:#000000 #66cc66",
    "map":           "bg:#000000 #44aa44",
    "map.water":     "bg:#000000 #2a5a2a",
    "map.road":      "bg:#000000 #66cc66",
    "map.label":     "bg:#000000 #88ee88",
}

_PAPER: Dict[str, str] = {
    "titlebar":      "bg:#c8b990 #000000 bold",
    "titlebar.dim":  "bg:#c8b990 #2a2410",
    "toolbar":       "bg:#e8dfc4 #000000",
    "toolbar.key":   "bg:#e8dfc4 #004400 bold",
    "toolbar.dim":   "bg:#e8dfc4 #3a3220",
    "statusbar":     "bg:#e8dfc4 #000000",
    "statusbar.warn": "bg:#e8dfc4 #880000 bold",
    "statusbar.dim": "bg:#e8dfc4 #3a3220",
    "compass":       "bg:#e8dfc4 #002266 bold",
    "crosshair":     "bg:#e8dfc4 #002266 bold reverse bold",
    "compass.label": "bg:#e8dfc4 #3a3220",
    "help":          "bg:#faf3df #000000",
    "help.title":    "bg:#faf3df #002266 bold",
    "help.key":      "bg:#faf3df #004400 bold",
    "help.text":     "bg:#faf3df #1a1408",
    "border":        "bg:#e8dfc4 #1a1408",
    "frame.border":  "bg:#e8dfc4 #1a1408",
    "button":        "bg:#c8b990 #000000",
    "button.focused": "bg:#002266 #ffffff bold",
    "dialog":        "bg:#faf3df #000000",
    "sidebar":             "bg:#f2e9cf #1a1408",
    "sidebar.title":       "bg:#c8b990 #000000 bold",
    "sidebar.tab":         "bg:#d8c9a0 #1a1408",
    "sidebar.tab.active":  "bg:#002266 #ffffff bold",
    "sidebar.section":     "bg:#f2e9cf #002266 bold",
    "sidebar.label":       "bg:#f2e9cf #4a3d20 bold",
    "sidebar.value":       "bg:#f2e9cf #000000",
    "sidebar.dim":         "bg:#f2e9cf #5a4d35",
    "sidebar.warn":        "bg:#f2e9cf #880000 bold",
    "sidebar.ok":          "bg:#f2e9cf #004400 bold",
    "sidebar.aircraft":          "bg:#f2e9cf #001a55",
    "sidebar.aircraft.selected": "bg:#002266 #ffffff bold",
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#cce0ff #000000 bold",
    "sidebar.hotkey":      "bg:#f2e9cf #004400 bold",
    "map":           "bg:#f2e9cf #000000",
    "map.water":     "bg:#f2e9cf #335577",
    "map.road":      "bg:#f2e9cf #1a0d00",
    "map.label":     "bg:#f2e9cf #000000 bold",
}

_RETRO: Dict[str, str] = {
    "titlebar":      "bg:#000000 #ddaa44",
    "titlebar.dim":  "bg:#000000 #664d11",
    "toolbar":       "bg:#000000 #cc8833",
    "toolbar.key":   "bg:#000000 #ddaa44",
    "toolbar.dim":   "bg:#000000 #553d0f",
    "statusbar":     "bg:#000000 #cc8833",
    "statusbar.warn": "bg:#000000 #cc8833 reverse",
    "statusbar.dim": "bg:#000000 #553d0f",
    "compass":       "bg:#000000 #ddaa44",
    "map":           "bg:#000000 #cc8833",
    "crosshair":     "bg:#000000 #ddaa44 reverse",
    "compass.label": "bg:#000000 #664d11",
    "help":          "bg:#000000 #cc8833",
    "help.title":    "bg:#000000 #ddaa44 reverse",
    "help.key":      "bg:#000000 #ddaa44",
    "help.text":     "bg:#000000 #cc8833",
    "border":        "bg:#000000 #664d11",
    "frame.border":  "bg:#000000 #664d11",
    "button":        "bg:#000000 #cc8833",
    "button.focused": "bg:#000000 #ddaa44 reverse",
    "dialog":        "bg:#000000 #cc8833",
    "dialog.body":   "bg:#000000 #cc8833",
    "dialog.shadow": "bg:#000000",
    "scrollbar.background": "bg:#000000",
    "scrollbar.button":     "bg:#000000 #cc8833 reverse",
    "sidebar":             "bg:#000000 #cc8833",
    "sidebar.title":       "bg:#000000 #cc8833",
    "sidebar.tab":         "bg:#000000 #553d0f",
    "sidebar.tab.active":  "bg:#000000 #ddaa44 reverse",
    "sidebar.section":     "bg:#000000 #ddaa44",
    "sidebar.label":       "bg:#000000 #664d11",
    "sidebar.value":       "bg:#000000 #cc8833",
    "sidebar.dim":         "bg:#000000 #553d0f",
    "sidebar.warn":        "bg:#000000 #cc8833 reverse",
    "sidebar.ok":          "bg:#000000 #ddaa44",
    "sidebar.aircraft":          "bg:#000000 #cc8833",
    "sidebar.aircraft.selected": "bg:#000000 #ddaa44 reverse",
    "sidebar.input":       "bg:#000000 #ddaa44 reverse",
    "sidebar.input.focus": "bg:#000000 #ffcc66 reverse",
    "sidebar.hotkey":      "bg:#000000 #ddaa44",
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
    "sidebar.title":       "bg:#1f2430 #7aa2f7",
    "sidebar.tab":         "bg:#1f2430 #565f89",
    "sidebar.tab.active":  "bg:#1a1b26 #c0caf5 reverse",
    "sidebar.section":     "bg:#1a1b26 #7aa2f7",
    "sidebar.label":       "bg:#1a1b26 #565f89",
    "sidebar.value":       "bg:#1a1b26 #c0caf5",
    "sidebar.dim":         "bg:#1a1b26 #414868",
    "sidebar.warn":        "bg:#1a1b26 #f7768e bold",
    "sidebar.ok":          "bg:#1a1b26 #9ece6a bold",
    "sidebar.aircraft":          "bg:#1a1b26 #c0caf5",
    "sidebar.aircraft.selected": "bg:#292e42 #ffffff bold",
    "sidebar.input":       "bg:#1f2430 #ffffff",
    "sidebar.input.focus": "bg:#292e42 #ffffff bold",
    "sidebar.hotkey":      "bg:#1a1b26 #9ece6a",
}

_LIGHT: Dict[str, str] = {
    "titlebar":      "bg:#b8c4d8 #000000 bold",
    "titlebar.dim":  "bg:#b8c4d8 #1a2030",
    "toolbar":       "bg:#dde2eb #000000",
    "toolbar.key":   "bg:#dde2eb #004400 bold",
    "toolbar.dim":   "bg:#dde2eb #2a3040",
    "statusbar":     "bg:#dde2eb #000000",
    "statusbar.warn": "bg:#dde2eb #880000 bold",
    "statusbar.dim": "bg:#dde2eb #2a3040",
    "compass":       "bg:#dde2eb #002266 bold",
    "map":           "bg:#dde2eb #002266",
    "crosshair":     "bg:#dde2eb #002266 bold reverse bold",
    "compass.label": "bg:#dde2eb #2a3040",
    "help":          "bg:#f0f3f8 #000000",
    "help.title":    "bg:#f0f3f8 #002266 bold",
    "help.key":      "bg:#f0f3f8 #004400 bold",
    "help.text":     "bg:#f0f3f8 #000000",
    "border":        "bg:#dde2eb #1a2030",
    "frame.border":  "bg:#dde2eb #1a2030",
    "button":        "bg:#b8c4d8 #000000",
    "button.focused": "bg:#002266 #ffffff bold",
    "dialog":        "bg:#f0f3f8 #000000",
    "sidebar":             "bg:#e6ebf3 #000000",
    "sidebar.title":       "bg:#b8c4d8 #000000 bold",
    "sidebar.tab":         "bg:#c6d0e0 #1a2030",
    "sidebar.tab.active":  "bg:#002266 #ffffff bold",
    "sidebar.section":     "bg:#e6ebf3 #002266 bold",
    "sidebar.label":       "bg:#e6ebf3 #2a3550 bold",
    "sidebar.value":       "bg:#e6ebf3 #000000",
    "sidebar.dim":         "bg:#e6ebf3 #455065",
    "sidebar.warn":        "bg:#e6ebf3 #880000 bold",
    "sidebar.ok":          "bg:#e6ebf3 #004400 bold",
    "sidebar.aircraft":          "bg:#e6ebf3 #001a55",
    "sidebar.aircraft.selected": "bg:#002266 #ffffff bold",
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#cce0ff #000000 bold",
    "sidebar.hotkey":      "bg:#e6ebf3 #004400 bold",
}

_HICON: Dict[str, str] = {
    "titlebar":      "bg:#000000 #ffffff bold",
    "titlebar.dim":  "bg:#000000 #c0c0c0",
    "toolbar":       "bg:#ffffff #000000 bold",
    "toolbar.key":   "bg:#ffffff #003300 bold",
    "toolbar.dim":   "bg:#ffffff #404040",
    "statusbar":     "bg:#ffffff #000000 bold",
    "statusbar.warn": "bg:#ffffff #aa0000 bold",
    "statusbar.dim": "bg:#ffffff #404040",
    "compass":       "bg:#ffffff #000088 bold",
    "map":           "bg:#ffffff #000088",
    "crosshair":     "bg:#ffffff #000088 bold reverse bold",
    "compass.label": "bg:#ffffff #404040",
    "help":          "bg:#ffffff #000000",
    "help.title":    "bg:#ffffff #000088 bold",
    "help.key":      "bg:#ffffff #003300 bold",
    "help.text":     "bg:#ffffff #000000",
    "border":        "bg:#ffffff #000000 bold",
    "frame.border":  "bg:#ffffff #000000 bold",
    "button":        "bg:#e0e0e0 #000000 bold",
    "button.focused": "bg:#000088 #ffffff bold",
    "dialog":        "bg:#ffffff #000000",
    "sidebar":             "bg:#ffffff #000000",
    "sidebar.title":       "bg:#000000 #ffffff bold",
    "sidebar.tab":         "bg:#d0d0d0 #000000 bold",
    "sidebar.tab.active":  "bg:#000088 #ffffff bold",
    "sidebar.section":     "bg:#ffffff #000088 bold",
    "sidebar.label":       "bg:#ffffff #000000 bold",
    "sidebar.value":       "bg:#ffffff #000000",
    "sidebar.dim":         "bg:#ffffff #404040",
    "sidebar.warn":        "bg:#ffffff #aa0000 bold",
    "sidebar.ok":          "bg:#ffffff #003300 bold",
    "sidebar.aircraft":          "bg:#ffffff #000088 bold",
    "sidebar.aircraft.selected": "bg:#000088 #ffffff bold",
    "sidebar.input":       "bg:#ffffff #000000 bold",
    "sidebar.input.focus": "bg:#ffff88 #000000 bold",
    "sidebar.hotkey":      "bg:#ffffff #003300 bold",
}

_EGA: Dict[str, str] = {
    "titlebar":      "bg:#0000aa #ffff55",
    "titlebar.dim":  "bg:#0000aa #aaaaaa",
    "toolbar":       "bg:#000000 #aaaaaa",
    "toolbar.key":   "bg:#000000 #ffff55",
    "toolbar.dim":   "bg:#000000 #555555",
    "statusbar":     "bg:#000000 #aaaaaa",
    "statusbar.warn": "bg:#000000 #ff5555",
    "statusbar.dim": "bg:#000000 #555555",
    "compass":       "bg:#000000 #ffff55",
    "crosshair":     "bg:#000000 #ffffff reverse",
    "compass.label": "bg:#000000 #aaaaaa",
    "help":          "bg:#000000 #aaaaaa",
    "help.title":    "bg:#0000aa #ffffff",
    "help.key":      "bg:#000000 #ffff55",
    "help.text":     "bg:#000000 #aaaaaa",
    "border":        "bg:#000000 #aaaaaa",
    "frame.border":  "bg:#000000 #aaaaaa",
    "button":        "bg:#aaaaaa #000000",
    "button.focused": "bg:#ffff55 #000000",
    "dialog":        "bg:#000000 #aaaaaa",
    "dialog.body":   "bg:#000000 #aaaaaa",
    "sidebar":             "bg:#000000 #aaaaaa",
    "sidebar.title":       "bg:#0000aa #ffffff",
    "sidebar.tab":         "bg:#000000 #555555",
    "sidebar.tab.active":  "bg:#000000 #ffff55 reverse",
    "sidebar.section":     "bg:#000000 #ffff55",
    "sidebar.label":       "bg:#000000 #555555",
    "sidebar.value":       "bg:#000000 #aaaaaa",
    "sidebar.dim":         "bg:#000000 #555555",
    "sidebar.warn":        "bg:#000000 #ff5555",
    "sidebar.ok":          "bg:#000000 #55ff55",
    "sidebar.aircraft":          "bg:#000000 #ffff55",
    "sidebar.aircraft.selected": "bg:#0000aa #ffffff",
    "sidebar.input":       "bg:#aaaaaa #000000",
    "sidebar.input.focus": "bg:#ffff55 #000000",
    "sidebar.hotkey":      "bg:#000000 #ffff55",
    "map":           "bg:#000000 #aaaaaa",
    "map.water":     "bg:#000000 #5555ff",
    "map.road":      "bg:#000000 #ffffff",
    "map.label":     "bg:#000000 #ffff55",
}

_WIN31: Dict[str, str] = {

    "titlebar":      "bg:#000080 #ffffff",
    "titlebar.dim":  "bg:#000080 #c0c0c0",

    "toolbar":       "bg:#c0c0c0 #000000",
    "toolbar.key":   "bg:#c0c0c0 #800000",
    "toolbar.dim":   "bg:#c0c0c0 #808080",

    "statusbar":     "bg:#c0c0c0 #000000",
    "statusbar.warn": "bg:#c0c0c0 #800000",
    "statusbar.dim": "bg:#c0c0c0 #808080",

    "compass":       "bg:#c0c0c0 #000000",
    "crosshair":     "bg:#000000 #ffff00 reverse",
    "compass.label": "bg:#c0c0c0 #808080",

    "help":          "bg:#c0c0c0 #000000",
    "help.title":    "bg:#000080 #ffffff",
    "help.key":      "bg:#c0c0c0 #800000",
    "help.text":     "bg:#c0c0c0 #000000",

    "border":        "bg:#c0c0c0 #000000",
    "frame.border":  "bg:#c0c0c0 #000000",

    "button":        "bg:#c0c0c0 #000000",
    "button.focused": "bg:#000080 #ffffff",

    "dialog":        "bg:#c0c0c0 #000000",
    "dialog.body":   "bg:#c0c0c0 #000000",

    "sidebar":             "bg:#c0c0c0 #000000",
    "sidebar.title":       "bg:#000080 #ffffff",
    "sidebar.tab":         "bg:#a0a0a0 #000000",
    "sidebar.tab.active":  "bg:#c0c0c0 #000000",
    "sidebar.section":     "bg:#000080 #ffffff",
    "sidebar.label":       "bg:#c0c0c0 #000000",
    "sidebar.value":       "bg:#c0c0c0 #000000",
    "sidebar.dim":         "bg:#c0c0c0 #808080",
    "sidebar.warn":        "bg:#c0c0c0 #800000",
    "sidebar.ok":          "bg:#c0c0c0 #008000",
    "sidebar.aircraft":          "bg:#c0c0c0 #800000",
    "sidebar.aircraft.selected": "bg:#000080 #ffffff",
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#ffffff #000080",
    "sidebar.hotkey":      "bg:#c0c0c0 #800000",

    "map":           "bg:#000000 #c0c0c0",
    "map.water":     "bg:#000000 #0000ff",
    "map.road":      "bg:#000000 #ffffff",
    "map.label":     "bg:#000000 #ffff00",
}

_NIGHT: Dict[str, str] = {
    "titlebar":      "bg:#000000 #c83232",
    "titlebar.dim":  "bg:#000000 #802020",
    "toolbar":       "bg:#000000 #c83232",
    "toolbar.key":   "bg:#000000 #ff5050",
    "toolbar.dim":   "bg:#000000 #501010",
    "statusbar":     "bg:#000000 #c83232",
    "statusbar.warn": "bg:#000000 #ffffff",
    "statusbar.dim": "bg:#000000 #501010",
    "compass":       "bg:#000000 #c83232",
    "crosshair":     "bg:#000000 #ff5050 reverse",
    "compass.label": "bg:#000000 #802020",
    "help":          "bg:#000000 #c83232",
    "help.title":    "bg:#000000 #ff5050",
    "help.key":      "bg:#000000 #ff5050",
    "help.text":     "bg:#000000 #c83232",
    "border":        "bg:#000000 #c83232",
    "frame.border":  "bg:#000000 #c83232",
    "button":        "bg:#300808 #c83232",
    "button.focused": "bg:#c83232 #000000",
    "dialog":        "bg:#000000 #c83232",
    "dialog.body":   "bg:#000000 #c83232",
    "sidebar":             "bg:#000000 #c83232",
    "sidebar.title":       "bg:#100404 #ff5050",
    "sidebar.tab":         "bg:#100404 #802020",
    "sidebar.tab.active":  "bg:#000000 #ff5050 reverse",
    "sidebar.section":     "bg:#000000 #ff5050",
    "sidebar.label":       "bg:#000000 #802020",
    "sidebar.value":       "bg:#000000 #c83232",
    "sidebar.dim":         "bg:#000000 #501010",
    "sidebar.warn":        "bg:#000000 #ffffff",
    "sidebar.ok":          "bg:#000000 #ff5050",
    "sidebar.aircraft":          "bg:#000000 #ff5050",
    "sidebar.aircraft.selected": "bg:#300808 #ffffff",
    "sidebar.input":       "bg:#100404 #c83232",
    "sidebar.input.focus": "bg:#300808 #ff5050",
    "sidebar.hotkey":      "bg:#000000 #ff5050",
    "map":           "bg:#000000 #c83232",
    "map.water":     "bg:#000000 #501010",
    "map.road":      "bg:#000000 #ff5050",
    "map.label":     "bg:#000000 #ff5050",
}

_THEMES: Dict[str, Dict[str, str]] = {
    "amber": _AMBER,
    "green": _GREEN,
    "paper": _PAPER,
    "retro": _RETRO,
    "dark":  _DARK,
    "light": _LIGHT,
    "hicon": _HICON,
    "ega":   _EGA,
    "win31": _WIN31,
    "night": _NIGHT,
}

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

_FORCE_ASCII_BORDER_THEMES = {"win31", "amber", "green", "retro", "dark", "night", "ega"}

def border_chars(style: str, theme: Optional[str] = None) -> dict:
    if theme is not None and theme in _FORCE_ASCII_BORDER_THEMES:
        return _BORDERS["ascii"]
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
    return tuple(_THEMES.keys())

def make_style(cfg: Config) -> Style:
    theme_name = cfg["ui"].get("theme", "amber")
    base = dict(_THEMES.get(theme_name, _AMBER))
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
    return _THEMES.get(theme, _AMBER)

_VECTOR_STYLES: Dict[str, Dict] = {
    "paper": dict(
        bg=(245, 240, 225),
        water=(180, 200, 220),
        park=(210, 230, 200),
        building=(220, 215, 200),
        road_color=(40, 30, 25),
        label_color=(20, 20, 20),
        halo_color=(245, 240, 225),
        aircraft_color=(180, 60, 30),
        aircraft_selected_color=(0, 0, 0),
        aircraft_emergency_color=(220, 0, 0),
        aircraft_label_color=(50, 30, 20),
        aircraft_halo_color=(245, 240, 225),
        road_colors={
            10: (20, 15, 10),  9: (35, 30, 25),   8: (50, 45, 40),
            7:  (65, 60, 55),  6: (80, 75, 70),    5: (95, 90, 85),
            4: (110, 105, 100), 3: (125, 120, 115), 2: (140, 135, 130),
            1: (155, 150, 145),
        },
    ),
    "light": dict(
        bg=(240, 240, 240),
        water=(170, 195, 220),
        park=(200, 225, 195),
        building=(215, 215, 215),
        road_color=(50, 50, 50),
        label_color=(30, 30, 30),
        halo_color=(240, 240, 240),
        aircraft_color=(0, 50, 150),
        aircraft_selected_color=(0, 0, 0),
        aircraft_emergency_color=(200, 0, 0),
        aircraft_label_color=(0, 50, 150),
        aircraft_halo_color=(240, 240, 240),
        road_colors={
            10: (30, 30, 30),  9: (45, 45, 45),   8: (60, 60, 60),
            7:  (75, 75, 75),  6: (90, 90, 90),    5: (105, 105, 105),
            4: (120, 120, 120), 3: (135, 135, 135), 2: (150, 150, 150),
            1: (165, 165, 165),
        },
    ),
    "hicon": dict(
        bg=(255, 255, 255),
        water=(140, 170, 200),
        park=(180, 220, 180),
        building=(200, 200, 200),
        road_color=(0, 0, 0),
        label_color=(0, 0, 0),
        halo_color=(255, 255, 255),
        aircraft_color=(0, 0, 136),
        aircraft_selected_color=(0, 0, 0),
        aircraft_emergency_color=(180, 0, 0),
        aircraft_label_color=(0, 0, 136),
        aircraft_halo_color=(255, 255, 255),
        road_colors={
            10: (0, 0, 0),    9: (15, 15, 15),   8: (30, 30, 30),
            7:  (45, 45, 45), 6: (60, 60, 60),    5: (75, 75, 75),
            4:  (90, 90, 90), 3: (105, 105, 105), 2: (120, 120, 120),
            1: (135, 135, 135),
        },
    ),
    "ega": dict(
        bg=(0, 0, 0),
        water=(0, 0, 170),
        park=(0, 170, 0),
        building=(170, 170, 170),
        road_color=(255, 255, 255),
        label_color=(255, 255, 85),
        halo_color=(0, 0, 0),
        aircraft_color=(255, 255, 85),
        aircraft_selected_color=(255, 255, 255),
        aircraft_emergency_color=(255, 85, 85),
        aircraft_label_color=(255, 255, 255),
        aircraft_halo_color=(0, 0, 0),
        road_colors={
            10: (255, 255, 255), 9: (255, 255, 85),   8: (255, 255, 85),
            7:  (170, 170, 170), 6: (170, 170, 170),  5: (85, 85, 85),
            4:  (85, 85, 85),   3: (85, 85, 85),      2: (85, 85, 85),
            1:  (85, 85, 85),
        },
    ),
    "win31": dict(
        bg=(0, 0, 0),
        water=(0, 0, 255),
        park=(0, 128, 0),
        building=(192, 192, 192),
        road_color=(255, 255, 255),
        label_color=(255, 255, 0),
        halo_color=(0, 0, 0),
        aircraft_color=(255, 255, 0),
        aircraft_selected_color=(255, 255, 255),
        aircraft_emergency_color=(255, 0, 0),
        aircraft_label_color=(255, 255, 255),
        aircraft_halo_color=(0, 0, 0),
        road_colors={
            10: (255, 255, 255), 9: (255, 255, 0),    8: (255, 255, 0),
            7:  (192, 192, 192), 6: (192, 192, 192),  5: (128, 128, 128),
            4:  (128, 128, 128), 3: (128, 128, 128),  2: (128, 128, 128),
            1:  (128, 128, 128),
        },
    ),
    "night": dict(
        bg=(0, 0, 0),
        water=(50, 0, 0),
        park=(80, 0, 0),
        building=(100, 0, 0),
        road_color=(220, 30, 30),
        label_color=(255, 80, 80),
        halo_color=(0, 0, 0),
        aircraft_color=(255, 60, 60),
        aircraft_selected_color=(255, 200, 200),
        aircraft_emergency_color=(255, 255, 255),
        aircraft_label_color=(255, 80, 80),
        aircraft_halo_color=(0, 0, 0),
        road_colors={
            10: (255, 50, 50),  9: (220, 40, 40),  8: (200, 35, 35),
            7:  (180, 30, 30),  6: (160, 25, 25),  5: (140, 20, 20),
            4:  (120, 15, 15),  3: (100, 10, 10),  2: (90, 8, 8),
            1:  (80, 5, 5),
        },
    ),
}

def theme_vector_style(
    theme: str,
    user_overrides: Optional[Dict] = None,
):
    from cartotui.raster_vector import ROAD_CLASS_PRIORITY, VectorStyle

    kw = _VECTOR_STYLES.get(theme)
    if kw is not None:
        style = VectorStyle(**kw)
    else:
        style = VectorStyle()

    if not user_overrides:
        return style

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
