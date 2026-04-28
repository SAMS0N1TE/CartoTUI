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
    # Maximum-contrast theme: black text on pure white, strong accent
    # colours for status/keys/aircraft. Designed for sunlight readability
    # and for users who need stronger differentiation than `light`/`paper`
    # provide. WCAG AAA where possible.
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
    # 16-color EGA palette. No bold (because in actual EGA mode there's
    # no bold-vs-regular distinction — bright colors are achieved by
    # picking a brighter palette index). Limited to the 16 hard-coded
    # EGA colors so the result looks period-correct.
    #
    # Picking from EGA's 64-color superset, mapped to the 16-color
    # default mode:
    #   black=#000000, blue=#0000aa, green=#00aa00, cyan=#00aaaa,
    #   red=#aa0000, magenta=#aa00aa, brown=#aa5500, lightgrey=#aaaaaa,
    #   darkgrey=#555555, brightblue=#5555ff, brightgreen=#55ff55,
    #   brightcyan=#55ffff, brightred=#ff5555, brightmagenta=#ff55ff,
    #   yellow=#ffff55, white=#ffffff
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
    "sidebar.tab.active":  "bg:#ffff55 #000000",
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
    # Windows 3.1 chrome. The desktop OS aesthetic from 1992: deep
    # navy title bars with white text, gray body panels with black
    # text, hard-edged buttons, no soft fades or rounded corners.
    #
    # Palette is the canonical Win 3.1 16-color VGA set:
    #   black    #000000      darkred    #800000
    #   darkgreen#008000      olive      #808000
    #   navy     #000080      magenta    #800080
    #   teal     #008080      lightgray  #c0c0c0
    #   gray     #808080      red        #ff0000
    #   green    #00ff00      yellow     #ffff00
    #   blue     #0000ff      pink       #ff00ff
    #   cyan     #00ffff      white      #ffffff
    #
    # No bold modifiers anywhere — Win 3.1 didn't have a "bold weight"
    # concept in the chrome, brightness came from picking a brighter
    # palette index. Section headers render as filled title-bar style
    # bars (white-on-navy) rather than colored bold text. Tabs use
    # hard rectangles. Borders are forced to ASCII characters by
    # ``border_chars()`` when this theme is active.

    # Title bar — the iconic Win 3.1 navy bar with white text.
    "titlebar":      "bg:#000080 #ffffff",
    "titlebar.dim":  "bg:#000080 #c0c0c0",

    # Toolbar — gray with black labels, like the standard menu bar.
    "toolbar":       "bg:#c0c0c0 #000000",
    "toolbar.key":   "bg:#c0c0c0 #800000",   # darkred for hotkey indicators
    "toolbar.dim":   "bg:#c0c0c0 #808080",

    # Status bar — same gray panel as toolbar.
    "statusbar":     "bg:#c0c0c0 #000000",
    "statusbar.warn": "bg:#c0c0c0 #800000",
    "statusbar.dim": "bg:#c0c0c0 #808080",

    # Compass / crosshair — black text on the gray sidebar bg.
    "compass":       "bg:#c0c0c0 #000000",
    "crosshair":     "bg:#000000 #ffff00 reverse",
    "compass.label": "bg:#c0c0c0 #808080",

    # Help dialog — gray panel with title-bar-style heading.
    "help":          "bg:#c0c0c0 #000000",
    "help.title":    "bg:#000080 #ffffff",
    "help.key":      "bg:#c0c0c0 #800000",
    "help.text":     "bg:#c0c0c0 #000000",

    # Borders — gray. The border_chars() function returns ASCII
    # chars for this theme so borders are 1-character + - | shapes.
    "border":        "bg:#c0c0c0 #000000",
    "frame.border":  "bg:#c0c0c0 #000000",

    # Buttons — gray with black text, navy when focused.
    "button":        "bg:#c0c0c0 #000000",
    "button.focused": "bg:#000080 #ffffff",

    # Dialogs.
    "dialog":        "bg:#c0c0c0 #000000",
    "dialog.body":   "bg:#c0c0c0 #000000",

    # Sidebar — the tabbed pane on the right. Body panel is gray.
    "sidebar":             "bg:#c0c0c0 #000000",
    # Title is the "CartoTUI" label at the top of the sidebar — gets
    # the title-bar treatment.
    "sidebar.title":       "bg:#000080 #ffffff",
    # Tabs — inactive tabs are gray-on-darker-gray (a sunken look).
    "sidebar.tab":         "bg:#a0a0a0 #000000",
    "sidebar.tab.active":  "bg:#c0c0c0 #000000",
    # Section headers ("Display", "Image", "View") — these are the
    # ones that should look like title bars per the Win 3.1
    # aesthetic. Filled navy bar with white text.
    "sidebar.section":     "bg:#000080 #ffffff",
    "sidebar.label":       "bg:#c0c0c0 #000000",
    "sidebar.value":       "bg:#c0c0c0 #000000",
    "sidebar.dim":         "bg:#c0c0c0 #808080",
    "sidebar.warn":        "bg:#c0c0c0 #800000",
    "sidebar.ok":          "bg:#c0c0c0 #008000",
    # Aircraft list rows — yellow for visibility on the gray panel,
    # navy bar when selected (matches title-bar style).
    "sidebar.aircraft":          "bg:#c0c0c0 #800000",
    "sidebar.aircraft.selected": "bg:#000080 #ffffff",
    # Inputs — white box with black text (Win 3.1 text controls
    # had a white field even when the panel was gray).
    "sidebar.input":       "bg:#ffffff #000000",
    "sidebar.input.focus": "bg:#ffffff #000080",
    "sidebar.hotkey":      "bg:#c0c0c0 #800000",

    # Map content (the basemap chrome — applies before vector overlay
    # paints). Black background like a CRT display.
    "map":           "bg:#000000 #c0c0c0",
    "map.water":     "bg:#000000 #0000ff",
    "map.road":      "bg:#000000 #ffffff",
    "map.label":     "bg:#000000 #ffff00",
}


_NIGHT: Dict[str, str] = {
    # Pure black + deep red. Designed for dark-adapted vision: no
    # whites, no blues, no greens. Aircraft emergencies render as
    # white as a deliberate exception (a flashing red dot on a red
    # field would be invisible).
    "titlebar":      "bg:#000000 #c83232",
    "titlebar.dim":  "bg:#000000 #802020",
    "toolbar":       "bg:#000000 #c83232",
    "toolbar.key":   "bg:#000000 #ff5050",
    "toolbar.dim":   "bg:#000000 #501010",
    "statusbar":     "bg:#000000 #c83232",
    "statusbar.warn": "bg:#000000 #ffffff",   # white for warnings only
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
    "sidebar.tab.active":  "bg:#c83232 #000000",
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
    "ascii":   {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+", "x": "+"},
    "heavy":   {"h": "━", "v": "┃", "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "x": "╋"},
    "rounded": {"h": "─", "v": "│", "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "x": "┼"},
}

# Themes that override the user's border_style preference. If the
# user picks one of these themes, borders force-fall-back to ASCII
# regardless of what they set in config — that's part of the visual
# identity of the theme. Win 3.1 used 1-pixel hard-edged borders
# which read closest to ASCII `+ - |` in a terminal.
_FORCE_ASCII_BORDER_THEMES = {"win31"}


def border_chars(style: str, theme: Optional[str] = None) -> dict:
    """Return the border-character set for the given style.

    If ``theme`` matches one of ``_FORCE_ASCII_BORDER_THEMES``, the
    style argument is ignored and we return ASCII borders. This
    keeps the chrome consistent with the theme's intended look —
    Win 3.1 doesn't make sense with `━┃┏┓` Unicode borders.
    """
    if theme is not None and theme in _FORCE_ASCII_BORDER_THEMES:
        return _BORDERS["ascii"]
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
