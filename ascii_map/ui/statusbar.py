#!/usr/bin/env python3
# ascii_map/ui/statusbar.py

from __future__ import annotations
from prompt_toolkit.widgets import Label
from prompt_toolkit.formatted_text import HTML

from ascii_map.ui.state import MapState
from ascii_map.config import Config

class StatusBar:
    def __init__(self, state: MapState, cfg: Config):
        self.state = state
        self.cfg = cfg
        self.label = Label("", style="class:status")

    def __pt_container__(self):
        self.update()
        return self.label

    def update(self):
        pal = self.cfg["map"].get("palette", "ascii_dense")
        mode = self.cfg["map"].get("mode", "ascii")
        color = "color" if self.cfg["render"].get("color", True) else "mono"
        msg = (
            f" lat={self.state.lat:.5f} lon={self.state.lon:.5f} "
            f"z={self.state.z} render={self.state.last_render_ms:.1f}ms "
            f"mode={mode}/{color} pal={pal}  {self.state.info_msg}"
        )
        self.label.text = HTML(msg)
        self.state.info_msg = ""