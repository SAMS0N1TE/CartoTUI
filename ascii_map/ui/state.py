#!/usr/bin/env python3
# ascii_map/ui/state.py
"""Mutable runtime state for the ASCII Map TUI."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Tuple

from ascii_map.config import Config
from ascii_map.geodesy import clamp_lat


def _wrap_lon(lon: float) -> float:
    """Wrap longitude to [-180, 180)."""

    lon = ((lon + 180.0) % 360.0) - 180.0
    # Avoid -180 exact to keep XYZ math stable
    return -179.999999 if lon <= -180.0 else lon


@dataclass
class MapState:
    cfg: Config

    # Map view
    lat: float = field(init=False)
    lon: float = field(init=False)
    z: int = field(init=False)
    min_zoom: int = field(init=False)
    max_zoom: int = field(init=False)

    # UI hints
    crosshair: str = field(init=False)
    last_render_ms: float = 0.0
    info_msg: str = ""

    # Compass
    heading_deg: float = 0.0  # 0 = North, increases clockwise
    _last_pan_vec: Tuple[int, int] = (0, 0)

    # Internal lock for multi-thread updates
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self):
        m = self.cfg["map"]
        self.lat = float(m.get("center_lat"))
        self.lon = float(m.get("center_lon"))
        self.z = int(m.get("zoom"))
        self.min_zoom = int(m.get("min_zoom"))
        self.max_zoom = int(m.get("max_zoom"))
        viewport = self.cfg["viewport"]
        if viewport.get("crosshair", True):
            self.crosshair = viewport.get("crosshair_char", "+") or "+"
        else:
            self.crosshair = ""
        # Clamp
        self._normalize_center()

    # ------------- normalization -------------

    def _normalize_center(self) -> None:
        self.lat = clamp_lat(self.lat)
        self.lon = _wrap_lon(self.lon)
        self.z = max(self.min_zoom, min(self.max_zoom, int(self.z)))

    # ------------- setters -------------

    def set_center(self, lat: float, lon: float) -> None:
        with self._lock:
            self.lat = clamp_lat(lat)
            self.lon = _wrap_lon(lon)

    def set_zoom(self, z: int) -> None:
        with self._lock:
            self.z = max(self.min_zoom, min(self.max_zoom, int(z)))

    def zoom_delta(self, dz: int) -> None:
        with self._lock:
            self.z = max(self.min_zoom, min(self.max_zoom, self.z + int(dz)))

    # ------------- compass / pan tracking -------------

    def record_pan(self, dx_cells: int, dy_cells: int) -> None:
        """Record a pan vector in terminal cell units for compass heading."""

        if dx_cells == 0 and dy_cells == 0:
            return
        with self._lock:
            self._last_pan_vec = (dx_cells, dy_cells)
            # Convert to screen-to-world: up (negative dy) = north
            # atan2(y, x) with y negative for north, then map to compass degrees.
            ang = math.degrees(math.atan2(dx_cells, -dy_cells))  # swap to get 0 at north
            if ang < 0:
                ang += 360.0
            self.heading_deg = ang

    # ------------- info -------------

    def set_info(self, msg: str) -> None:
        with self._lock:
            self.info_msg = msg

    # ------------- export -------------

    def snapshot(self) -> Tuple[float, float, int, float]:
        """Return a quick snapshot used by render threads."""

        with self._lock:
            return self.lat, self.lon, self.z, self.heading_deg
