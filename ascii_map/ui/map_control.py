#!/usr/bin/env python3
# ascii_map/ui/map_control.py
"""prompt_toolkit UIControl that renders the live map view."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image
from prompt_toolkit.application import get_app_or_none
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import UIContent, UIControl

from ascii_map.cache import TileCache
from ascii_map.composite import composite_from_tiles
from ascii_map.rendering.renderer import Renderer
from ascii_map.ui.state import MapState


@dataclass
class Frame:
    width: int
    height: int
    lines_frag: List[List[Tuple[str, str]]]


class MapControl(UIControl):
    """Render map imagery in the terminal and react to pan/zoom input."""

    def __init__(self, cfg, state: MapState, renderer: Renderer):
        self.cfg = cfg
        self.state = state
        self.renderer = renderer

        ncfg = cfg["network"]
        self.cache = TileCache(
            ncfg["tile_url"],
            Path(cfg["cache"]["dir"]),
            ncfg["user_agent"],
        )
        self._req_q: queue.Queue = queue.Queue(maxsize=2)
        self._res_q: queue.Queue = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._render_worker, daemon=True)
        self._thread.start()

        # Track the most recent terminal dimensions so interaction-triggered
        # renders know the correct size to request.
        self._last_width = 1
        self._last_height = 1
        self._last_frame: Optional[Frame] = None
        self._window = None

    # -------- UIControl interface --------

    def is_focusable(self) -> bool:
        return True

    def preferred_width(self, max_available_width: int) -> int:
        return max_available_width

    def preferred_height(
        self,
        width: int,
        max_available_height: int,
        wrap_lines: bool,
        get_line_prefix,
    ) -> int:
        return max_available_height

    def create_content(self, width: int, height: int) -> UIContent:
        width = max(1, int(width))
        height = max(1, int(height))
        self._last_width = width
        self._last_height = height

        latest_frame = self._drain_results()
        if latest_frame is not None:
            self._last_frame = latest_frame

        frame = self._last_frame
        if frame is None:
            self._enqueue(width, height, self.state.lat, self.state.lon, self.state.z)
            return self._blank_content(width, height)

        if frame.width != width or frame.height != height:
            # Request a fresh render sized for the new viewport but keep showing
            # the last frame to avoid flashing blank output.
            self._enqueue(width, height, self.state.lat, self.state.lon, self.state.z)

        lines_frag = self._normalize_lines(frame, width, height)

        # Crosshair overlay after padding
        chx, chy = width // 2, height // 2
        if self.state.crosshair and 0 <= chy < height and 0 <= chx < width:
            row_text = lines_frag[chy][0][1]
            row_text = row_text[:chx] + self.state.crosshair + row_text[chx + 1 :]
            lines_frag[chy] = [("", row_text)]

        return UIContent(
            get_line=lambda i: lines_frag[i] if 0 <= i < height else [("", " " * width)],
            line_count=height,
            cursor_position=Point(x=chx, y=chy),
        )

    def bind_window(self, window) -> None:
        """Remember the Window that hosts this control for focus management."""

        self._window = window

    def focus(self) -> None:
        app = get_app_or_none()
        if app and self._window is not None:
            app.layout.focus(self._window)

    # -------- worker logic --------

    def _enqueue(self, w: int, h: int, lat: float, lon: float, z: int) -> None:
        w = max(1, int(w))
        h = max(1, int(h))
        with self._req_q.mutex:
            self._req_q.queue.clear()
        try:
            self._req_q.put_nowait((w, h, lat, lon, z))
        except queue.Full:
            pass

    def _render_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._req_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if job is None or self._stop.is_set():
                break

            w, h, lat, lon, z = job
            t0 = time.time()
            try:
                max_px = int(self.cfg["map"].get("max_composite_px", 1200))
                px_w = min(max_px, max(64, int(w * 8)))
                px_h = min(max_px, max(64, int(h * 16)))
                img = composite_from_tiles(
                    self.cache,
                    lat,
                    lon,
                    z,
                    px_w,
                    px_h,
                    overzoom_levels=int(self.cfg["map"].get("overzoom", 2)),
                    contrast=float(self.cfg["render"].get("contrast", 1.0)),
                    sharpen_percent=int(self.cfg["render"].get("sharpen_percent", 200)),
                    sharpen_radius=float(self.cfg["render"].get("sharpen_radius", 2.0)),
                    sharpen_threshold=int(self.cfg["render"].get("sharpen_threshold", 3)),
                    edge_boost=bool(self.cfg["render"].get("edge_boost", False)),
                    invert=bool(self.cfg["render"].get("invert", False)),
                )
            except Exception:
                img = Image.new("RGB", (max(64, int(w * 8)), max(64, int(h * 16))), (0, 0, 0))

            lines = self.renderer.render(
                img,
                w,
                h,
                bool(self.cfg["render"].get("color", True)),
                self.cfg["map"].get("mode", "ascii"),
                self.cfg["map"].get("palette", "ascii_dense"),
            )
            self.state.last_render_ms = (time.time() - t0) * 1000.0
            frame = Frame(w, h, lines)

            with self._res_q.mutex:
                self._res_q.queue.clear()
            try:
                self._res_q.put_nowait(frame)
            except queue.Full:
                pass

            app = get_app_or_none()
            if app:
                app.invalidate()

    # -------- helpers --------

    def _drain_results(self) -> Optional[Frame]:
        frame: Optional[Frame] = None
        while True:
            try:
                frame = self._res_q.get_nowait()
            except queue.Empty:
                break
        return frame

    @staticmethod
    def _blank_content(width: int, height: int) -> UIContent:
        empty_line = [("", " " * width)]
        return UIContent(
            get_line=lambda i: empty_line if 0 <= i < height else [("", " " * width)],
            line_count=height,
        )

    @staticmethod
    def _normalize_lines(frame: Frame, width: int, height: int) -> List[List[Tuple[str, str]]]:
        lines_frag: List[List[Tuple[str, str]]] = []
        source = frame.lines_frag
        for y in range(height):
            if y < len(source) and source[y]:
                row_text = "".join(text for (_style, text) in source[y])
                if len(row_text) < width:
                    row_text = row_text.ljust(width)
                else:
                    row_text = row_text[:width]
                lines_frag.append([("", row_text)])
            else:
                lines_frag.append([("", " " * width)])
        return lines_frag

    # -------- lifecycle / user actions --------

    def shutdown(self) -> None:
        self._stop.set()
        with self._req_q.mutex:
            self._req_q.queue.clear()
        try:
            self._req_q.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=0.5)

    def pan(self, dx: int, dy: int) -> None:
        lat_step = 0.1 * (2 ** (-self.state.z))
        lon_step = 0.1 * (2 ** (-self.state.z))
        self.state.lat -= dy * lat_step
        self.state.lon += dx * lon_step
        self.state._normalize_center()
        self.state.record_pan(dx, dy)
        self.state.set_info(f"Moved to {self.state.lat:.4f},{self.state.lon:.4f}")
        self.request_render()

    def zoom(self, delta: int) -> None:
        self.state.zoom_delta(delta)
        self.state.set_info(f"Zoom {self.state.z}")
        self.request_render()

    def request_render(self) -> None:
        # Let the worker trigger repaint; keeps mouse clicks smooth.
        self._enqueue(
            self._last_width,
            self._last_height,
            self.state.lat,
            self.state.lon,
            self.state.z,
        )
