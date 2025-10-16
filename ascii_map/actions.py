#!/usr/bin/env python3
# ascii_map/actions.py
"""
Shared action functions used by both keybindings and toolbar buttons.
Each action modifies MapState and triggers MapControl re-render.
"""

from __future__ import annotations
from ascii_map.ui.map_control import MapControl
from ascii_map.ui.state import MapState


def pan(state: MapState, control: MapControl, dx: int, dy: int):
    state.set_info(f"Pan {dx:+d},{dy:+d}")
    control.pan(dx, dy)


def zoom(state: MapState, control: MapControl, delta: int):
    state.set_info(f"Zoom {('in' if delta > 0 else 'out')}")
    control.zoom(delta)


def toggle_help(state: MapState):
    state.set_info("Press 'h' to toggle help window.")


def quit_app():
    import sys
    sys.exit(0)
