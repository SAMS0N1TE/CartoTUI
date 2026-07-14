
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image
from prompt_toolkit.application import get_app_or_none
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from cartotui.cache import TileCache
from cartotui.composite import composite_from_tiles, prefetch_ring
from cartotui.raster_vector import rasterise_view
from cartotui.rendering.renderer import Renderer
from cartotui.themes import theme_vector_style
from cartotui.traffic.aircraft import AircraftRegistry
from cartotui.ui.aircraft_overlay import apply_aircraft_overlay
from cartotui.ui.map_overlay import apply_vector_overlay
from cartotui.ui.state import MapState
from cartotui.vector_source import VectorTileSource

log = logging.getLogger("cartotui.map")

@dataclass
class _Frame:
    width: int
    height: int
    rows: List[List[Tuple[str, str]]]
    snapshot_key: Tuple

class MapControl(UIControl):

    def __init__(
        self,
        cfg,
        state: MapState,
        renderer: Renderer,
        cache: TileCache,
        vector_source: Optional[VectorTileSource] = None,
        aircraft_registry: Optional[AircraftRegistry] = None,
        on_select_aircraft=None,
    ):
        self.cfg = cfg
        self.state = state
        self.renderer = renderer
        self.cache = cache
        self.vector_source = vector_source
        self.aircraft_registry = aircraft_registry
        self.on_select_aircraft = on_select_aircraft
        self.widget_manager = None
        self.radar_source = None

        self._raster_caches: dict = {}
        self._vector_sources: dict = {}
        if cache is not None:
            self._raster_caches[cache.url_template] = cache
        if vector_source is not None:
            self._vector_sources[id(vector_source)] = vector_source

        self._req_q: queue.Queue[Optional[Tuple]] = queue.Queue(maxsize=2)
        self._res_q: queue.Queue[_Frame] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._render_worker, daemon=True, name="render")
        self._worker.start()

        self._last_w = 1
        self._last_h = 1
        self._last_frame: Optional[_Frame] = None
        self._window = None

        self._dedup_lock = threading.Lock()
        self._inflight_key: Optional[Tuple] = None
        self._last_enqueued_key: Optional[Tuple] = None

        self._drag_anchor: Optional[Tuple[int, int]] = None
        self._drag_lat: Optional[float] = None
        self._drag_lon: Optional[float] = None
        self._drag_moved = False
        self._mouse_was_down = False

        self._pan_until = 0.0
        self._last_render_panning = False

    def _mark_panning(self) -> None:
        self._pan_until = time.monotonic() + 0.16

    def _panning(self) -> bool:
        return (bool(self.cfg["render"].get("dynamic_quality", True))
                and time.monotonic() < self._pan_until)

    def swap_to_source(self, source) -> None:
        from pathlib import Path

        cache_dir = Path(self.cfg["cache"]["dir"])
        ncfg = self.cfg["network"]

        if source.kind == "raster":
            cache = self._raster_caches.get(source.url_template)
            if cache is None:
                cache = TileCache(
                    url_template=source.url_template,
                    cache_dir=cache_dir,
                    user_agent=ncfg["user_agent"],
                    connect_timeout=float(ncfg["connect_timeout_s"]),
                    read_timeout=float(ncfg["read_timeout_s"]),
                    retries=int(ncfg["retries"]),
                    parallel_downloads=int(ncfg["parallel_downloads"]),
                )
                self._raster_caches[source.url_template] = cache
            self.cache = cache
            self.state.set_source("raster")
        else:
            v_cfg = dict(self.cfg["vector"])
            v_cfg["source"] = source.vector_backend or "mvt_url"
            if source.vector_backend == "protomaps_api":
                v_cfg["protomaps_api_url"] = source.url_template
            elif source.vector_backend == "pmtiles_url":
                v_cfg["pmtiles_url"] = source.pmtiles_url or source.url_template
            else:
                v_cfg["mvt_url"] = source.url_template
            cache_key = (v_cfg.get("source", ""),
                         v_cfg.get("protomaps_api_url", ""),
                         v_cfg.get("pmtiles_url", ""),
                         v_cfg.get("mvt_url", ""))
            vsrc = self._vector_sources.get(cache_key)
            if vsrc is None:
                vsrc = VectorTileSource(
                    v_cfg,
                    cache_dir=cache_dir / "vector",
                    user_agent=ncfg["user_agent"],
                )
                self._vector_sources[cache_key] = vsrc
            self.vector_source = vsrc
            self.state.set_source("vector")

        self.request_render()

    def is_focusable(self) -> bool:
        return True

    def preferred_width(self, max_available_width: int) -> int:
        return max_available_width

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return max_available_height

    def create_content(self, width: int, height: int) -> UIContent:
        width = max(1, int(width))
        height = max(1, int(height))
        size_changed = (width != self._last_w) or (height != self._last_h)
        self._last_w = width
        self._last_h = height

        latest = self._drain_results()
        if latest is not None:
            self._last_frame = latest

        snap = self.state.snapshot()
        ac_gen = self.aircraft_registry.generation if self.aircraft_registry else 0
        ac_sel = self.state.selected_aircraft_icao or ""
        snap_key = (width, height, ac_gen, ac_sel) + snap
        if (
            self._last_frame is None
            or self._last_frame.snapshot_key != snap_key
            or size_changed
        ):
            self._enqueue(width, height, snap, snap_key)

        if self._last_frame is None:
            return self._blank(width, height)

        rows = self._normalise_rows(self._last_frame, width, height)
        chx, chy = width // 2, height // 2
        cross_row = None
        if self.state.crosshair and 0 <= chy < height and 0 <= chx < width:
            cross_row = self._overlay_crosshair(rows[chy], chx, self.state.crosshair)

        def get_line(i: int):
            if i == chy and cross_row is not None:
                return cross_row
            return rows[i] if 0 <= i < height else [("", " " * width)]

        return UIContent(
            get_line=get_line,
            line_count=height,
            cursor_position=Point(x=chx, y=chy),
        )

    def mouse_handler(self, mouse_event: MouseEvent):
        if not self.cfg["ui"].get("mouse", True):
            return NotImplemented
        et = mouse_event.event_type
        x = mouse_event.position.x
        y = mouse_event.position.y

        wm = self.widget_manager
        if wm is not None and wm.is_dragging():
            if et == MouseEventType.MOUSE_MOVE:
                wm.drag_to(x, y)
            elif et == MouseEventType.MOUSE_UP:
                wm.end_drag()
            elif et == MouseEventType.MOUSE_DOWN:
                wm.end_drag(save=False)
            return None

        if et == MouseEventType.SCROLL_UP:
            self.zoom(+1)
            return None
        if et == MouseEventType.SCROLL_DOWN:
            self.zoom(-1)
            return None

        if et == MouseEventType.MOUSE_DOWN:
            self._drag_anchor = (x, y)
            self._drag_lat = self.state.lat
            self._drag_lon = self.state.lon
            self._drag_moved = False
            self._mouse_was_down = True
            return None

        if et == MouseEventType.MOUSE_MOVE and self._mouse_was_down:
            if self._drag_anchor is None:
                return None
            ax, ay = self._drag_anchor
            dx = x - ax
            dy = y - ay
            if dx == 0 and dy == 0:
                return None
            self.state.set_center(self._drag_lat, self._drag_lon)
            self.state.pan_cells(-dx, -dy)
            self._drag_moved = True
            self._mark_panning()
            self.request_render()
            return None

        if et == MouseEventType.MOUSE_UP:
            self._mouse_was_down = False
            anchor = self._drag_anchor
            self._drag_anchor = None
            if not self._drag_moved and anchor is not None:
                if self._click_to_aircraft(x, y):
                    pass
                else:
                    self._click_to_center(x, y)
            self._drag_lat = None
            self._drag_lon = None
            self._drag_moved = False
            return None

        return NotImplemented

    def _click_to_aircraft(self, cell_x: int, cell_y: int) -> bool:
        if self.aircraft_registry is None or self.on_select_aircraft is None:
            return False
        positioned = self.aircraft_registry.with_position()
        if not positioned:
            return False
        from cartotui.geodesy import viewport_deg_per_cell
        cell_w_px, cell_h_px = self._cell_pixel_size()
        cw, ch = self._last_w, self._last_h
        if cw < 2 or ch < 2:
            return False
        cx_off = cell_x - cw // 2
        cy_off = cell_y - ch // 2
        d_lon, d_lat = viewport_deg_per_cell(self.state.lat, self.state.z,
                                             cell_w_px, cell_h_px)
        click_lat = self.state.lat - cy_off * d_lat
        click_lon = self.state.lon + cx_off * d_lon
        tol_lat = abs(d_lat) * 2.0
        tol_lon = abs(d_lon) * 2.0
        best = None
        best_d = 1e9
        for ac in positioned:
            dlat = abs(ac.lat - click_lat)
            dlon = abs(ac.lon - click_lon)
            if dlat > tol_lat or dlon > tol_lon:
                continue
            score = (dlat / max(1e-9, abs(d_lat))) ** 2 + (dlon / max(1e-9, abs(d_lon))) ** 2
            if score < best_d:
                best_d = score
                best = ac
        if best is None:
            return False
        cur = self.state.selected_aircraft_icao
        new = None if (cur and cur.upper() == best.icao.upper()) else best.icao
        self.on_select_aircraft(new)
        return True

    def _click_to_center(self, cell_x: int, cell_y: int) -> None:
        cw, ch = self._last_w, self._last_h
        if cw < 2 or ch < 2:
            return
        cell_w_px, cell_h_px = self._cell_pixel_size()
        z = self.state.z
        cx_off_cells = cell_x - cw // 2
        cy_off_cells = cell_y - ch // 2
        from cartotui.geodesy import viewport_deg_per_cell
        d_lon, d_lat = viewport_deg_per_cell(self.state.lat, z, cell_w_px, cell_h_px)
        new_lat = self.state.lat - cy_off_cells * d_lat
        new_lon = self.state.lon + cx_off_cells * d_lon
        self.state.set_center(new_lat, new_lon)
        self.state.set_info(f"Centered on {new_lat:.4f}, {new_lon:.4f}")
        self.request_render()

    def bind_window(self, window) -> None:
        self._window = window

    def focus(self) -> None:
        app = get_app_or_none()
        if app and self._window is not None:
            try:
                app.layout.focus(self._window)
            except Exception:
                pass

    def pan(self, dx_cells: int, dy_cells: int) -> None:
        cw, ch = self._cell_pixel_size()
        self.state.pan_cells(dx_cells, dy_cells, cw, ch)
        self.state.set_info(f"Pan ({dx_cells:+d}, {dy_cells:+d})")
        self._mark_panning()
        self.request_render()

    def zoom(self, delta: int) -> None:
        old = self.state.z
        self.state.zoom_delta(delta)
        if self.state.z != old:
            self.state.set_info(f"Zoom {self.state.z}")
        self.request_render()

    def goto(self, lat: float, lon: float, z: Optional[int] = None) -> None:
        self.state.set_center(lat, lon)
        if z is not None:
            self.state.set_zoom(z)
        self.state.set_info(f"Goto {lat:.4f}, {lon:.4f}")
        self.request_render()

    def request_render(self, force: bool = False) -> None:
        snap = self.state.snapshot()
        snap_key = None
        if force:
            self._force_nonce = getattr(self, "_force_nonce", 0) + 1
            ac_gen = self.aircraft_registry.generation if self.aircraft_registry else 0
            ac_sel = self.state.selected_aircraft_icao or ""
            snap_key = (self._last_w, self._last_h, ac_gen, ac_sel,
                        self._force_nonce) + snap
        self._enqueue(self._last_w, self._last_h, snap, snap_key)
        app = get_app_or_none()
        if app:
            app.invalidate()

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._req_q.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=float(self.cfg["app"].get("shutdown_timeout_s", 3.0)))
        self.cache.close()
        if self.vector_source is not None:
            self.vector_source.close()

    def _enqueue(self, w: int, h: int, snap: Tuple, snap_key: Optional[Tuple] = None) -> None:
        if w < 1 or h < 1:
            return
        if snap_key is None:
            ac_gen = self.aircraft_registry.generation if self.aircraft_registry else 0
            ac_sel = self.state.selected_aircraft_icao or ""
            snap_key = (w, h, ac_gen, ac_sel) + snap
        with self._dedup_lock:
            if self._inflight_key == snap_key:
                return
            if (self._last_enqueued_key == snap_key
                    and self._req_q.qsize() > 0):
                return
            self._last_enqueued_key = snap_key
        with self._req_q.mutex:
            self._req_q.queue.clear()
        try:
            self._req_q.put_nowait((w, h, snap, snap_key))
        except queue.Full:
            pass

    def _render_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._req_q.get(timeout=0.1)
            except queue.Empty:
                if self._last_render_panning and not self._panning():
                    self._last_render_panning = False
                    self.request_render(force=True)
                continue
            if job is None or self._stop.is_set():
                break

            w, h, snap, snap_key = job
            (lat, lon, z, source, render_mode, palette, color, dither,
             theme, shaded, brightness, contrast, threshold_mode, _src_idx) = snap

            with self._dedup_lock:
                self._inflight_key = snap_key

            cell_w_px, cell_h_px = self.renderer.cell_pixel_size(render_mode)
            max_px = int(self.cfg["map"].get("max_composite_px", 1400))
            panning = self._panning()
            self._last_render_panning = panning
            scale = int(self.cfg["render"].get("vector_scale", 6)) if source == "vector" else 4
            px_w = max(64, min(max_px, w * cell_w_px * scale))
            px_h = max(64, min(max_px, h * cell_h_px * scale))

            self.renderer.update_options(
                shaded_blocks=shaded,
                subpixel_threshold=threshold_mode,
            )

            r = self.cfg["render"]
            t0 = time.time()
            img = None
            ac_overlay = []
            sel_icao = self.state.selected_aircraft_icao
            if self.aircraft_registry is not None:
                ac_overlay = self.aircraft_registry.with_position()

            try:
                theme_overrides = self.cfg.data.get("theme", {})
            except Exception:
                theme_overrides = {}
            style = theme_vector_style(theme, theme_overrides)
            if bool(self.cfg["render"].get("road_highlight", False)):
                from cartotui.themes import apply_road_highlight
                apply_road_highlight(style)

            if source == "vector" and self.vector_source is not None:
                engine = self.cfg["render"].get("vector_engine", "libcarto")
                if engine == "libcarto":
                    try:
                        from cartotui.rendering.libcarto_backend import rasterise_view_libcarto
                        pf_enable = bool(self.cfg["prefetch"].get("enable", True))
                        img = rasterise_view_libcarto(
                            self.vector_source, lat, lon, z, px_w, px_h, style=style,
                            preload=pf_enable and not panning,
                            cached_only=panning,
                        )
                        if panning:
                            try:
                                self.vector_source.prefetch_viewport(lat, lon, z, px_w, px_h)
                            except Exception:
                                pass
                    except Exception as e:
                        log.warning("libcarto rasterise failed (%s); using python path", e)
                        img = None
                    if img is None and panning:
                        try:
                            bg = (style.bg.r, style.bg.g, style.bg.b)
                        except Exception:
                            bg = (24, 26, 32)
                        img = Image.new("RGB", (px_w, px_h), bg)
                if img is None:
                    try:
                        img = rasterise_view(
                            self.vector_source, lat, lon, z, px_w, px_h, style=style,
                            aircraft_overlay=None,
                            selected_icao=None,
                        )
                    except Exception as e:
                        log.warning("Vector rasterise failed: %s", e)
                        img = None
                if img is not None:
                    v_gamma = 1.0 if panning else float(r.get("gamma", 1.0))
                    if (abs(brightness - 1.0) > 1e-3 or abs(contrast - 1.0) > 1e-3
                            or abs(v_gamma - 1.0) > 1e-3):
                        from cartotui.composite import apply_image_adjustments
                        img = apply_image_adjustments(
                            img, brightness=brightness, contrast=contrast,
                            gamma=v_gamma)

            if img is None:
                cfg_sharpen = int(r.get("sharpen_percent", 150))
                if render_mode in ("quadrant", "braille") and threshold_mode == "edge":
                    sharpen = 0
                elif render_mode in ("quadrant", "braille"):
                    sharpen = min(80, cfg_sharpen)
                else:
                    sharpen = cfg_sharpen
                overzoom = int(self.cfg["map"].get("overzoom", 2))
                if panning:
                    sharpen = 0
                    overzoom = max(overzoom, 5)
                try:
                    img = composite_from_tiles(
                        self.cache,
                        lat, lon, z,
                        px_w, px_h,
                        overzoom_levels=overzoom,
                        contrast=float(contrast),
                        brightness=float(brightness),
                        gamma=1.0 if panning else float(r.get("gamma", 1.0)),
                        sharpen_percent=sharpen,
                        sharpen_radius=float(r.get("sharpen_radius", 1.5)),
                        sharpen_threshold=int(r.get("sharpen_threshold", 3)),
                        edge_boost=False if panning else bool(r.get("edge_boost", False)),
                        invert=bool(r.get("invert", False)),
                        cached_only=panning,
                    )
                except Exception as e:
                    log.warning("Composite failed: %s", e)
                    img = Image.new("RGB", (px_w, px_h), (24, 26, 32))

                if img is not None and self.cfg["render"].get("raster_tint", "none") == "theme":
                    try:
                        from PIL import ImageOps
                        hi = max((style.road_color, style.label_color),
                                 key=lambda c: c[0] + c[1] + c[2])
                        img = ImageOps.colorize(
                            img.convert("L"),
                            black=tuple(style.bg), white=tuple(hi), mid=tuple(style.building),
                        )
                    except Exception as e:
                        log.debug("raster tint failed: %s", e)

            if img is not None:
                img = self._apply_radar(img, lat, lon, z)

            effective_color = bool(color)

            try:
                rows = self.renderer.render(
                    img, w, h, effective_color, render_mode, palette, dither
                )
            except Exception as e:
                log.warning("Render failed: %s", e)
                rows = [[("", " " * w)] for _ in range(h)]

            r_cfg = self.cfg["render"]
            vector_overlay_enabled = bool(r_cfg.get("vector_overlay", True))
            boundaries_enabled = bool(r_cfg.get("boundaries", True)) and not panning
            if (self.vector_source is not None
                    and (vector_overlay_enabled or boundaries_enabled)):
                try:
                    apply_vector_overlay(
                        rows, self.vector_source,
                        center_lat=lat, center_lon=lon, z=z,
                        term_w=w, term_h=h,
                        canvas_px_w=px_w, canvas_px_h=px_h,
                        style=style,
                        max_labels=64 if vector_overlay_enabled else 0,
                        draw_boundaries=boundaries_enabled,
                    )
                except Exception as e:
                    log.debug("Vector overlay failed: %s", e)

            if ac_overlay:
                try:
                    trails_cfg = self.cfg.get("aircraft_trails", {})
                    trails_enabled = bool(trails_cfg.get("enabled", True))
                    trails_duration = float(trails_cfg.get("duration_s", 60.0))
                    apply_aircraft_overlay(
                        rows, ac_overlay,
                        center_lat=lat, center_lon=lon, z=z,
                        term_w=w, term_h=h,
                        canvas_px_w=px_w, canvas_px_h=px_h,
                        style=style,
                        selected_icao=sel_icao,
                        show_trails=trails_enabled,
                        trail_duration_s=trails_duration,
                    )
                except Exception as e:
                    log.debug("Aircraft post-render overlay failed: %s", e)

            self.state.last_render_ms = (time.time() - t0) * 1000.0

            frame = _Frame(
                w, h, rows,
                snap_key,
            )
            with self._res_q.mutex:
                self._res_q.queue.clear()
            try:
                self._res_q.put_nowait(frame)
            except queue.Full:
                pass

            if source == "raster":
                pf = self.cfg["prefetch"]
                if pf.get("enable", True):
                    try:
                        max_inflight = int(pf.get("max_inflight", 4))
                        want = []
                        if panning:
                            from cartotui.composite import tiles_for_view
                            vis = tiles_for_view(lat, lon, z, px_w, px_h)[0]
                            want = list(vis)
                        ring = list(prefetch_ring(
                            self.cache, lat, lon, z, px_w, px_h,
                            ring_radius=int(pf.get("ring_radius", 1)),
                        ))
                        combined = want + ring[:max_inflight]
                        if combined:
                            self.cache.prefetch(combined)
                    except Exception as e:
                        log.debug("Prefetch failed: %s", e)

            app = get_app_or_none()
            if app:
                app.invalidate()

            with self._dedup_lock:
                if self._inflight_key == snap_key:
                    self._inflight_key = None

    def _cell_pixel_size(self) -> Tuple[int, int]:
        return self.renderer.cell_pixel_size(self.state.render_mode)

    def _apply_radar(self, img, lat, lon, z, cached_only: bool = True):
        rd = self.cfg.get("overlays", {}).get("radar", {})
        if not rd.get("enabled") or self.radar_source is None or img is None:
            return img
        try:
            return self.radar_source.composite_onto(
                img, lat, lon, z, img.width, img.height,
                opacity=float(rd.get("opacity", 0.65)),
                color=int(rd.get("color", 4)),
                smooth=int(rd.get("smooth", 1)),
                snow=int(rd.get("snow", 1)),
                which=rd.get("frame", "latest"),
                cached_only=cached_only,
            )
        except Exception as e:
            log.debug("radar overlay failed: %s", e)
            return img

    def snapshot_png(self, path: str, long_side: int = 2048) -> str:
        from cartotui.themes import apply_road_highlight, theme_vector_style
        term_w = max(20, self._last_w)
        term_h = max(10, self._last_h)
        long_side = max(512, min(4096, int(long_side)))
        aw, ah = term_w * 8, term_h * 16
        s = long_side / float(max(aw, ah))
        px_w = max(64, int(aw * s))
        px_h = max(64, int(ah * s))

        lat, lon, z = self.state.lat, self.state.lon, self.state.z
        theme = self.state.theme
        source = self.state.source
        try:
            theme_overrides = self.cfg.data.get("theme", {})
        except Exception:
            theme_overrides = {}
        style = theme_vector_style(theme, theme_overrides)
        if bool(self.cfg["render"].get("road_highlight", False)):
            apply_road_highlight(style)

        img = None
        if source == "vector" and self.vector_source is not None:
            engine = self.cfg["render"].get("vector_engine", "libcarto")
            if engine == "libcarto":
                try:
                    from cartotui.rendering.libcarto_backend import rasterise_view_libcarto
                    img = rasterise_view_libcarto(self.vector_source, lat, lon, z, px_w, px_h, style=style)
                except Exception:
                    img = None
            if img is None:
                try:
                    img = rasterise_view(self.vector_source, lat, lon, z, px_w, px_h, style=style)
                except Exception:
                    img = None
        if img is None:
            r = self.cfg["render"]
            img = composite_from_tiles(
                self.cache, lat, lon, z, px_w, px_h,
                overzoom_levels=int(self.cfg["map"].get("overzoom", 2)),
                contrast=float(self.state.contrast), brightness=float(self.state.brightness),
                gamma=float(r.get("gamma", 1.0)),
                sharpen_percent=int(r.get("sharpen_percent", 150)),
                sharpen_radius=float(r.get("sharpen_radius", 1.5)),
                sharpen_threshold=int(r.get("sharpen_threshold", 3)),
                edge_boost=bool(r.get("edge_boost", False)),
                invert=bool(r.get("invert", False)),
            )
            if self.cfg["render"].get("raster_tint", "none") == "theme":
                from PIL import ImageOps
                hi = max((style.road_color, style.label_color), key=lambda c: sum(c))
                img = ImageOps.colorize(img.convert("L"), black=tuple(style.bg),
                                        white=tuple(hi), mid=tuple(style.building))
        else:
            from cartotui.composite import apply_image_adjustments
            img = apply_image_adjustments(
                img, brightness=float(self.state.brightness),
                contrast=float(self.state.contrast),
                gamma=float(self.cfg["render"].get("gamma", 1.0)))

        img = self._apply_radar(img, lat, lon, z, cached_only=False)
        img.save(path)
        return path

    def snapshot_html(self, path: str) -> str:
        from cartotui.snapshot import save_html
        frame = self._last_frame
        rows = frame.rows if frame is not None else []
        return save_html(rows, self.state.theme, path, title="CartoTUI map")

    def _drain_results(self) -> Optional[_Frame]:
        frame: Optional[_Frame] = None
        while True:
            try:
                frame = self._res_q.get_nowait()
            except queue.Empty:
                break
        return frame

    @staticmethod
    def _blank(width: int, height: int) -> UIContent:
        empty = [("", " " * width)]
        return UIContent(
            get_line=lambda i: empty if 0 <= i < height else [("", " " * width)],
            line_count=height,
        )

    @staticmethod
    def _normalise_rows(frame: _Frame, width: int, height: int):
        src = frame.rows
        if frame.width == width and frame.height == height and len(src) == height:
            return src
        out = []
        for y in range(height):
            if y < len(src) and src[y]:
                runs = []
                consumed = 0
                for style, text in src[y]:
                    remaining = width - consumed
                    if remaining <= 0:
                        break
                    if len(text) <= remaining:
                        runs.append((style, text))
                        consumed += len(text)
                    else:
                        runs.append((style, text[:remaining]))
                        consumed = width
                        break
                if consumed < width:
                    runs.append(("", " " * (width - consumed)))
                out.append(runs)
            else:
                out.append([("", " " * width)])
        return out

    @staticmethod
    def _overlay_crosshair(row, x: int, ch: str):
        out = []
        consumed = 0
        replaced = False
        for style, text in row:
            tlen = len(text)
            if not replaced and consumed <= x < consumed + tlen:
                local = x - consumed
                if local > 0:
                    out.append((style, text[:local]))
                out.append(("class:crosshair", ch))
                rest = text[local + 1:]
                if rest:
                    out.append((style, rest))
                replaced = True
            else:
                out.append((style, text))
            consumed += tlen
        if not replaced:
            out.append(("class:crosshair", ch))
        return out
