
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from cartotui.config import Config
from cartotui.geodesy import clamp_lat, viewport_deg_per_cell, wrap_lon

__all__ = ["MapState"]

@dataclass
class MapState:
    cfg: Config

    lat: float = field(init=False)
    lon: float = field(init=False)
    z: int = field(init=False)
    min_zoom: int = field(init=False)
    max_zoom: int = field(init=False)

    source: str = field(init=False)
    render_mode: str = field(init=False)
    palette: str = field(init=False)
    color: bool = field(init=False)
    dither: str = field(init=False)
    crosshair: str = field(init=False)
    theme: str = field(init=False)
    shaded_blocks: bool = field(init=False)

    brightness: float = field(init=False)
    contrast: float = field(init=False)
    threshold_mode: str = field(init=False)

    current_look: str = field(init=False, default="")

    source_idx: int = field(init=False, default=0)

    last_render_ms: float = 0.0
    last_snapshot: str = ""
    info_msg: str = ""
    info_msg_until: float = 0.0
    heading_deg: float = 0.0
    pending_input: str = ""

    sidebar_visible: bool = True
    sidebar_tab: int = 0
    selected_aircraft_icao: Optional[str] = None

    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        m = self.cfg["map"]
        self.lat = float(m["center_lat"])
        self.lon = float(m["center_lon"])
        self.z = int(m["zoom"])
        self.min_zoom = int(m["min_zoom"])
        self.max_zoom = int(m["max_zoom"])

        mode = str(m.get("mode", "vector"))
        rcfg = self.cfg["render"]
        _modes = ("ascii", "quadrant", "braille", "half")
        vrm = str(rcfg.get("vector_render_mode", "quadrant"))
        vrm = vrm if vrm in _modes else "quadrant"
        rrm = str(rcfg.get("raster_render_mode", "ascii"))
        rrm = rrm if rrm in _modes else "ascii"
        if mode == "vector":
            self.source = "vector"
            self.render_mode = vrm
        else:
            self.source = "raster"
            self.render_mode = mode if mode in _modes else rrm
        self._mode_for = {"vector": vrm, "raster": rrm}
        self._mode_for[self.source] = self.render_mode

        self.palette = str(m.get("palette", "shades"))

        r = self.cfg["render"]
        self.color = bool(r.get("color", True))
        self.dither = str(r.get("dither", "none"))
        self.shaded_blocks = bool(r.get("shaded_blocks", False))
        self.brightness = float(r.get("brightness", 1.0))
        self.contrast = float(r.get("contrast", 1.05))
        self.threshold_mode = str(r.get("subpixel_threshold", "adaptive"))

        vp = self.cfg["viewport"]
        self.crosshair = (vp.get("crosshair_char") or "+") if vp.get("crosshair", True) else ""

        self.theme = str(self.cfg["ui"].get("theme", "amber"))

        try:
            from cartotui import looks
            self.current_look = looks.current_look_key(self, self.cfg) or ""
        except Exception:
            self.current_look = ""

        self._normalize_center()

    def _normalize_center(self) -> None:
        self.lat = clamp_lat(self.lat)
        self.lon = wrap_lon(self.lon)
        self.z = max(self.min_zoom, min(self.max_zoom, int(self.z)))

    def set_center(self, lat: float, lon: float) -> None:
        with self._lock:
            self.lat = clamp_lat(lat)
            self.lon = wrap_lon(lon)

    def set_zoom(self, z: int) -> None:
        with self._lock:
            self.z = max(self.min_zoom, min(self.max_zoom, int(z)))

    def zoom_delta(self, dz: int) -> None:
        with self._lock:
            self.z = max(self.min_zoom, min(self.max_zoom, self.z + int(dz)))

    def pan_cells(
        self,
        dx_cells: int,
        dy_cells: int,
        cell_w_px: int = 8,
        cell_h_px: int = 16,
    ) -> None:
        if dx_cells == 0 and dy_cells == 0:
            return
        with self._lock:
            d_lon, d_lat = viewport_deg_per_cell(self.lat, self.z, cell_w_px, cell_h_px)
            self.lat = clamp_lat(self.lat - dy_cells * d_lat)
            self.lon = wrap_lon(self.lon + dx_cells * d_lon)
            self._update_heading(dx_cells, dy_cells)

    def _update_heading(self, dx: int, dy: int) -> None:
        ang = math.degrees(math.atan2(dx, -dy))
        if ang < 0:
            ang += 360.0
        self.heading_deg = ang

    def set_render_mode(self, mode: str) -> None:
        with self._lock:
            if mode in ("ascii", "quadrant", "braille", "half"):
                self.render_mode = mode
                self._mode_for[self.source] = mode

    def cycle_render_mode(self) -> None:
        with self._lock:
            order = ["ascii", "quadrant", "braille", "half"]
            i = order.index(self.render_mode) if self.render_mode in order else 0
            self.render_mode = order[(i + 1) % len(order)]
            self._mode_for[self.source] = self.render_mode

    def set_source(self, kind: str) -> None:
        with self._lock:
            if kind not in ("vector", "raster") or kind == self.source:
                return
            self._mode_for[self.source] = self.render_mode
            self.source = kind
            self.render_mode = self._mode_for.get(kind, self.render_mode)

    def toggle_source(self) -> None:
        self.set_source("raster" if self.source == "vector" else "vector")

    def toggle_shaded(self) -> None:
        with self._lock:
            self.shaded_blocks = not self.shaded_blocks

    def cycle_theme(self) -> None:
        with self._lock:
            try:
                from cartotui.themes import available_themes
                order = list(available_themes())
            except Exception:
                order = ["amber", "green", "paper", "retro", "dark", "light", "hicon"]
            i = order.index(self.theme) if self.theme in order else 0
            self.theme = order[(i + 1) % len(order)]

    def cycle_palette(self, palettes: list) -> None:
        with self._lock:
            if not palettes:
                return
            try:
                i = palettes.index(self.palette)
            except ValueError:
                i = -1
            self.palette = palettes[(i + 1) % len(palettes)]

    def cycle_dither(self) -> None:
        with self._lock:
            order = ["none", "bayer", "atkinson", "floyd"]
            i = order.index(self.dither) if self.dither in order else 0
            self.dither = order[(i + 1) % len(order)]

    def toggle_color(self) -> None:
        with self._lock:
            self.color = not self.color

    def adjust_brightness(self, delta: float) -> None:
        with self._lock:
            self.brightness = max(0.2, min(3.0, self.brightness + delta))

    def adjust_contrast(self, delta: float) -> None:
        with self._lock:
            self.contrast = max(0.2, min(3.0, self.contrast + delta))

    def reset_image_adjust(self) -> None:
        with self._lock:
            self.brightness = 1.0
            self.contrast = 1.05

    def cycle_threshold(self) -> None:
        with self._lock:
            order = ["adaptive", "percentile", "edge", "fixed"]
            i = order.index(self.threshold_mode) if self.threshold_mode in order else 0
            self.threshold_mode = order[(i + 1) % len(order)]

    def toggle_sidebar(self) -> None:
        with self._lock:
            self.sidebar_visible = not self.sidebar_visible

    def set_sidebar_tab(self, idx: int) -> None:
        with self._lock:
            self.sidebar_tab = max(0, min(4, int(idx)))

    def select_aircraft(self, icao: Optional[str]) -> None:
        with self._lock:
            self.selected_aircraft_icao = icao.upper() if icao else None

    def set_info(self, msg: str, ttl_s: float = 3.0) -> None:
        with self._lock:
            self.info_msg = msg
            self.info_msg_until = time.monotonic() + ttl_s

    def current_info(self) -> str:
        with self._lock:
            if not self.info_msg:
                return ""
            if time.monotonic() > self.info_msg_until:
                return ""
            return self.info_msg

    def snapshot(self) -> Tuple:
        with self._lock:
            return (
                self.lat,
                self.lon,
                self.z,
                self.source,
                self.render_mode,
                self.palette,
                self.color,
                self.dither,
                self.theme,
                self.shaded_blocks,
                self.brightness,
                self.contrast,
                self.threshold_mode,
                self.source_idx,
            )
