#!/usr/bin/env python3
# ascii_map/ui/buttons.py
"""
Minimal flat button primitives for the TUI toolbar and other clickable areas.
Extends prompt_toolkit's Button with simplified style and consistent layout.
"""

from prompt_toolkit.widgets import Button
from prompt_toolkit.formatted_text import HTML

def make_button(label: str, handler, style: str = "class:button") -> Button:
    """
    Create a button with a consistent minimalist look.
    """
    btn = Button(text=HTML(f"<b>{label}</b>"), handler=handler)
    btn.window.style = style
    return btn
