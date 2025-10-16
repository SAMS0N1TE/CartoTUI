#!/usr/bin/env python3
# ascii_map/styles.py
"""
Style definitions for the ASCII Map TUI.
Provides light, dark, and auto themes for prompt_toolkit.
"""

from prompt_toolkit.styles import Style
from ascii_map.config import Config

def make_style(cfg: Config) -> Style:
    theme = cfg["ui"].get("theme", "auto")

    base_dark = {
        "toolbar": "bg:#202020 #ffffff",
        "status": "bg:#303030 #cccccc",
        "compass": "fg:#00ff00 bold",
        "help": "bg:#202020 #dddddd",
        "button": "bg:#444444 #ffffff",
    }
    base_light = {
        "toolbar": "bg:#dddddd #000000",
        "status": "bg:#cccccc #000000",
        "compass": "fg:#006600 bold",
        "help": "bg:#eeeeee #000000",
        "button": "bg:#bbbbbb #000000",
    }

    if theme == "light":
        return Style.from_dict(base_light)
    if theme == "dark":
        return Style.from_dict(base_dark)

    # Auto-detect via environment or terminal background
    try:
        import os
        if os.getenv("TERM_THEME", "").lower() == "light":
            return Style.from_dict(base_light)
    except Exception:
        pass

    return Style.from_dict(base_dark)
