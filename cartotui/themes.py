"""Prompt-toolkit style dictionaries for CartoTUI themes.

Three themes:

  * `retro`  — amber/green CRT-inspired palette with heavy borders
  * `dark`   — a neutral dark theme
  * `light`  — a neutral light theme

The map itself is rendered with raw RGB foregrounds, so themes only style the
chrome (titlebar, statusbar, toolbar, compass, help pane, dialogs).
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

from cartotui.config import Config

__all__ = ["make_style", "border_chars", "theme_palette"]


_AMBER = {
    "titlebar":      "bg:#1a0f00 #ffaa33 bold",
    "titlebar.dim":  "bg:#1a0f00 #886611",
    "toolbar":       "bg:#0f0f0f #ffaa33",
    "toolbar.key":   "bg:#0f0f0f #ffdd66 bold",
    "toolbar.dim":   "bg:#0f0f0f #553300",
    "statusbar":     "bg:#0f0f0f #ffaa33",
    "statusbar.warn": "bg:#0f0f0f #ff5555 bold",
    "statusbar.dim": "bg:#0f0f0f #553300",
    "compass":       "bg:#0f0f0f #ffcc66 bold",
    "crosshair":    "bg:#0f0f0f #ffcc66 bold reverse bold",
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
    # Map cells (vector mode draws white-on-dark, theme tints them):
    "map":           "bg:#0a0500 #ffaa33",
    "map.water":     "bg:#0a0500 #553311",
    "map.road":      "bg:#0a0500 #ffdd66",
    "map.label":     "bg:#0a0500 #ffffaa bold",
}

_GREEN = {
    "titlebar":      "bg:#001100 #66ff66 bold",
    "titlebar.dim":  "bg:#001100 #226622",
    "toolbar":       "bg:#000a00 #66ff66",
    "toolbar.key":   "bg:#000a00 #aaffaa bold",
    "toolbar.dim":   "bg:#000a00 #114411",
    "statusbar":     "bg:#000a00 #66ff66",
    "statusbar.warn": "bg:#000a00 #ff5555 bold",
    "statusbar.dim": "bg:#000a00 #114411",
    "compass":       "bg:#000a00 #aaffaa bold",
    "crosshair":    "bg:#000a00 #aaffaa bold reverse bold",
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
    "map":           "bg:#000500 #66ff66",
    "map.water":     "bg:#000500 #114411",
    "map.road":      "bg:#000500 #aaffaa",
    "map.label":     "bg:#000500 #ddffdd bold",
}

_PAPER = {
    "titlebar":      "bg:#dddddd #000000 bold",
    "titlebar.dim":  "bg:#dddddd #555555",
    "toolbar":       "bg:#eeeeee #000000",
    "toolbar.key":   "bg:#eeeeee #006600 bold",
    "toolbar.dim":   "bg:#eeeeee #888888",
    "statusbar":     "bg:#eeeeee #000000",
    "statusbar.warn": "bg:#eeeeee #aa0000 bold",
    "statusbar.dim": "bg:#eeeeee #888888",
    "compass":       "bg:#eeeeee #003388 bold",
    "crosshair":    "bg:#eeeeee #003388 bold reverse bold",
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
    "map":           "bg:#f5f0e0 #000000",
    "map.water":     "bg:#f5f0e0 #88aabb",
    "map.road":      "bg:#f5f0e0 #221100",
    "map.label":     "bg:#f5f0e0 #000000 bold",
}


_RETRO = {
    "titlebar":      "bg:#1a0f00 #ffaa33 bold",
    "titlebar.dim":  "bg:#1a0f00 #886611",
    "toolbar":       "bg:#0f0f0f #ffaa33",
    "toolbar.key":   "bg:#0f0f0f #66ff66 bold",
    "toolbar.dim":   "bg:#0f0f0f #555555",
    "statusbar":     "bg:#0f0f0f #88ff88",
    "statusbar.warn": "bg:#0f0f0f #ff5555 bold",
    "statusbar.dim": "bg:#0f0f0f #555555",
    "compass":       "bg:#0f0f0f #ffaa33 bold",
    "map":          "bg:#0f0f0f #ffaa33",
    "crosshair":    "bg:#0f0f0f #ffaa33 bold reverse bold",
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
}

_DARK = {
    "titlebar":      "bg:#1f2430 #c0caf5 bold",
    "titlebar.dim":  "bg:#1f2430 #565f89",
    "toolbar":       "bg:#16161e #c0caf5",
    "toolbar.key":   "bg:#16161e #9ece6a bold",
    "toolbar.dim":   "bg:#16161e #565f89",
    "statusbar":     "bg:#16161e #c0caf5",
    "statusbar.warn": "bg:#16161e #f7768e bold",
    "statusbar.dim": "bg:#16161e #565f89",
    "compass":       "bg:#16161e #7aa2f7 bold",
    "map":          "bg:#16161e #7aa2f7",
    "crosshair":    "bg:#16161e #7aa2f7 bold reverse bold",
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
}

_LIGHT = {
    "titlebar":      "bg:#dddddd #000000 bold",
    "titlebar.dim":  "bg:#dddddd #555555",
    "toolbar":       "bg:#eeeeee #000000",
    "toolbar.key":   "bg:#eeeeee #006600 bold",
    "toolbar.dim":   "bg:#eeeeee #555555",
    "statusbar":     "bg:#eeeeee #000000",
    "statusbar.warn": "bg:#eeeeee #aa0000 bold",
    "statusbar.dim": "bg:#eeeeee #555555",
    "compass":       "bg:#eeeeee #003388 bold",
    "map":          "bg:#eeeeee #003388",
    "crosshair":    "bg:#eeeeee #003388 bold reverse bold",
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
}


_BORDERS = {
    "ascii":   {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+", "x": "+"},
    "heavy":   {"h": "━", "v": "┃", "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "x": "╋"},
    "rounded": {"h": "─", "v": "│", "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "x": "┼"},
}


def border_chars(style: str) -> dict:
    return _BORDERS.get(style, _BORDERS["heavy"])


def make_style(cfg: Config) -> Style:
    theme = cfg["ui"].get("theme", "amber")
    if theme == "amber":
        return Style.from_dict(_AMBER)
    if theme == "green":
        return Style.from_dict(_GREEN)
    if theme == "paper":
        return Style.from_dict(_PAPER)
    if theme == "light":
        return Style.from_dict(_LIGHT)
    if theme == "dark":
        return Style.from_dict(_DARK)
    return Style.from_dict(_RETRO)


def theme_palette(theme: str) -> dict:
    """Return the colour dict for a theme — used by the map renderer to know
    what RGB to draw with so it complements the chrome."""
    return {
        "amber": _AMBER, "green": _GREEN, "paper": _PAPER,
        "retro": _RETRO, "dark": _DARK, "light": _LIGHT,
    }.get(theme, _AMBER)
