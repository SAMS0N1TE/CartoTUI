from __future__ import annotations

import io
import logging
import math
import threading
import time
from typing import Optional

import numpy as np
from PIL import Image

from cartotui.geodesy import latlon_to_tile_xy

log = logging.getLogger("cartotui.radar")

_MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
_META_TTL_S = 180.0
RADAR_MAX_Z = 7
RADAR_MAX_PX = 768


def _is_precip_tile(tile: Image.Image) -> bool:
    a = np.asarray(tile.resize((32, 32)))
    if a.shape[-1] < 4:
        return True
    op = a[..., 3] > 0
    if not op.any():
        return False
    rgb = a[..., :3].astype(int)
    colored = (
        (np.abs(rgb[..., 0] - rgb[..., 1]) > 16)
        | (np.abs(rgb[..., 1] - rgb[..., 2]) > 16)
        | (np.abs(rgb[..., 0] - rgb[..., 2]) > 16)
    )
    return bool((colored & op).any())


class RadarSource:
    def __init__(self, user_agent: str = "CartoTUI", tile_size: int = 256) -> None:
        self.user_agent = user_agent
        self.tile_size = tile_size
        self._host: Optional[str] = None
        self._past = []
        self._nowcast = []
        self._frames_all = []
        self._frame_time = None
        self._frame_path = None
        self._last_meta = 0.0
        self._last_latest_seen = None
        self.animate = False
        self._anim_idx = 0
        self._prefetch_sig = None
        self._prefetch_cur_sig = None
        self._cache = {}
        self._lru = []
        self._lock = threading.Lock()
        self._inflight = 0
        self.max_px = RADAR_MAX_PX
        self.on_tiles_ready: Optional[callable] = None

    def loading(self) -> int:
        """Number of radar tiles currently being fetched in the background."""
        with self._lock:
            return self._inflight

    def _radar_plan(self, z, px_w, px_h):
        """Choose the radar zoom + working resolution so the viewport is covered
        by only a few tiles. Returns (rz, scale, rpx_w, rpx_h)."""
        rz = min(int(z), RADAR_MAX_Z)
        while rz > 1:
            scale = 2 ** (z - rz)
            rpx_w = max(1, px_w // scale)
            rpx_h = max(1, px_h // scale)
            if max(rpx_w, rpx_h) <= self.max_px:
                return rz, scale, rpx_w, rpx_h
            rz -= 1
        scale = 2 ** (z - rz)
        return rz, scale, max(1, px_w // scale), max(1, px_h // scale)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._lru.clear()

    def force_refresh(self) -> None:
        self.clear_cache()
        self.refresh_frames(force=True)

    def refresh_frames(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self._frame_path and (now - self._last_meta) < _META_TTL_S:
            return
        self._last_meta = now
        try:
            import requests
            r = requests.get(_MAPS_URL, headers={"User-Agent": self.user_agent}, timeout=8)
            r.raise_for_status()
            j = r.json()
            self._host = j.get("host") or "https://tilecache.rainviewer.com"
            radar = j.get("radar") or {}
            self._past = radar.get("past") or []
            self._nowcast = radar.get("nowcast") or []
            self._frames_all = list(self._past) + list(self._nowcast)
        except Exception as e:
            log.debug("radar meta fetch failed: %s", e)

    def _static_frame(self, which: str):
        if which == "nowcast" and self._nowcast:
            return self._nowcast[-1]
        if self._past:
            return self._past[-1]
        if self._nowcast:
            return self._nowcast[0]
        return None

    def _active_frame(self, which: str):
        if self.animate and self._frames_all:
            return self._frames_all[self._anim_idx % len(self._frames_all)]
        return self._static_frame(which)

    def frame_count(self) -> int:
        return len(self._frames_all)

    def anim_index(self) -> int:
        n = len(self._frames_all)
        return (self._anim_idx % n) if n else 0

    def advance(self, step: int = 1) -> None:
        n = len(self._frames_all)
        if n:
            self._anim_idx = (self._anim_idx + step) % n

    def latest_changed(self) -> bool:
        lf = self._past[-1] if self._past else (self._nowcast[-1] if self._nowcast else None)
        t = lf.get("time") if lf else None
        changed = (t is not None and t != self._last_latest_seen)
        self._last_latest_seen = t
        return changed

    def frame_label(self) -> str:
        if self._frame_time is None:
            return "no data"
        dt = time.time() - float(self._frame_time)
        if abs(dt) < 60:
            return "now"
        m = int(round(dt / 60.0))
        return f"{m}m ago" if m > 0 else f"+{-m}m"

    def _tile_for(self, frame_time, frame_path, z, x, y, color, smooth, snow):
        if not (self._host and frame_path):
            return None
        key = (frame_time, z, x, y, color, smooth, snow, self.tile_size)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        url = (f"{self._host}{frame_path}/{self.tile_size}"
               f"/{z}/{x}/{y}/{color}/{smooth}_{snow}.png")
        tile = None
        try:
            import requests
            r = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=8)
            if r.status_code == 200 and r.content:
                tile = Image.open(io.BytesIO(r.content)).convert("RGBA")
                if not _is_precip_tile(tile):
                    tile = None
        except Exception as e:
            log.debug("radar tile fetch failed: %s", e)
            tile = None
        with self._lock:
            self._cache[key] = tile
            self._lru.append(key)
            if len(self._lru) > 2048:
                old = self._lru.pop(0)
                self._cache.pop(old, None)
        return tile

    def _get_tile(self, z, x, y, color, smooth, snow):
        return self._tile_for(self._frame_time, self._frame_path, z, x, y, color, smooth, snow)

    def _get_cached(self, z, x, y, color, smooth, snow):
        """Cache-only lookup: never touches the network (safe on the render
        thread). Returns None for both 'not fetched yet' and 'no precipitation'."""
        key = (self._frame_time, z, x, y, color, smooth, snow, self.tile_size)
        with self._lock:
            return self._cache.get(key)

    def _tile_coords(self, lat, lon, z, px_w, px_h):
        rz, scale, rpx_w, rpx_h = self._radar_plan(z, px_w, px_h)
        tp = self.tile_size
        xt, yt = latlon_to_tile_xy(lat, lon, rz)
        wl = xt * tp - rpx_w / 2.0
        wt = yt * tp - rpx_h / 2.0
        n = 2 ** rz
        coords = []
        for ty in range(math.floor(wt / tp), math.floor((wt + rpx_h) / tp) + 1):
            if not (0 <= ty < n):
                continue
            for tx in range(math.floor(wl / tp), math.floor((wl + rpx_w) / tp) + 1):
                coords.append((tx % n, ty))
        return rz, coords

    def _prefetch(self, lat, lon, z, px_w, px_h, color, smooth, snow, frames):
        """Load every not-yet-cached tile for `frames` over the viewport in a
        single background batch, then invoke on_tiles_ready once when done."""
        if not frames:
            return
        rz, coords = self._tile_coords(lat, lon, z, px_w, px_h)

        todo = []
        for f in frames:
            t, p = f.get("time"), f.get("path")
            for (x, y) in coords:
                key = (t, rz, x, y, color, smooth, snow, self.tile_size)
                with self._lock:
                    if key in self._cache:
                        continue
                todo.append((t, p, x, y))
        if not todo:
            return

        with self._lock:
            self._inflight += len(todo)

        def one(t, p, x, y):
            try:
                self._tile_for(t, p, rz, x, y, color, smooth, snow)
                return 1
            finally:
                with self._lock:
                    self._inflight -= 1

        def work():
            from concurrent.futures import ThreadPoolExecutor
            added = 0
            try:
                with ThreadPoolExecutor(max_workers=8) as ex:
                    futs = [ex.submit(one, t, p, x, y) for (t, p, x, y) in todo]
                    added = sum(fu.result() for fu in futs)
            except Exception:
                pass
            if added and self.on_tiles_ready is not None:
                try:
                    self.on_tiles_ready()
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True).start()

    def prefetch_viewport(self, lat, lon, z, px_w, px_h, color=4, smooth=1, snow=1):
        self._prefetch(lat, lon, z, px_w, px_h, color, smooth, snow,
                       list(self._frames_all))

    def _maybe_prefetch(self, lat, lon, z, px_w, px_h, color, smooth, snow):
        """Animation: keep every frame's tiles warm for the viewport."""
        frames = self._frames_all
        if not frames:
            return
        sig = (round(lat, 2), round(lon, 2), int(z), len(frames),
               frames[0].get("time"), frames[-1].get("time"))
        if sig == self._prefetch_sig:
            return
        self._prefetch_sig = sig
        self._prefetch(lat, lon, z, px_w, px_h, color, smooth, snow, list(frames))

    def _maybe_prefetch_current(self, lat, lon, z, px_w, px_h, color, smooth, snow):
        """Static: only the currently shown frame needs to be loaded."""
        frame = self._active_frame("latest")
        if frame is None:
            return
        sig = (round(lat, 2), round(lon, 2), int(z),
               self._frame_time, color, smooth, snow)
        if sig == self._prefetch_cur_sig:
            return
        self._prefetch_cur_sig = sig
        self._prefetch(lat, lon, z, px_w, px_h, color, smooth, snow, [frame])

    def composite_onto(self, base: Image.Image, lat: float, lon: float, z: int,
                       px_w: int, px_h: int, opacity: float = 0.65, color: int = 4,
                       smooth: int = 1, snow: int = 1, which: str = "latest",
                       cached_only: bool = True) -> Image.Image:
        if not cached_only:
            self.refresh_frames()
        frame = self._active_frame(which)
        if not frame:
            return base
        self._frame_time = frame.get("time")
        self._frame_path = frame.get("path")

        if cached_only:
            if self.animate:
                self._maybe_prefetch(lat, lon, z, px_w, px_h, color, smooth, snow)
            else:
                self._maybe_prefetch_current(lat, lon, z, px_w, px_h, color, smooth, snow)
        getter = self._get_cached if cached_only else self._get_tile

        tp = self.tile_size
        rz, scale, rpx_w, rpx_h = self._radar_plan(z, px_w, px_h)

        xt, yt = latlon_to_tile_xy(lat, lon, rz)
        world_left = xt * tp - rpx_w / 2.0
        world_top = yt * tp - rpx_h / 2.0
        n = 2 ** rz
        tx_min = math.floor(world_left / tp)
        tx_max = math.floor((world_left + rpx_w) / tp)
        ty_min = math.floor(world_top / tp)
        ty_max = math.floor((world_top + rpx_h) / tp)

        layer = Image.new("RGBA", (rpx_w, rpx_h), (0, 0, 0, 0))
        drew = 0
        for ty in range(ty_min, ty_max + 1):
            if not (0 <= ty < n):
                continue
            for tx in range(tx_min, tx_max + 1):
                tile = getter(rz, tx % n, ty, color, smooth, snow)
                if tile is None:
                    continue
                sx = int(round(tx * tp - world_left))
                sy = int(round(ty * tp - world_top))
                layer.paste(tile, (sx, sy), tile)
                drew += 1
        if drew == 0:
            return base

        if (rpx_w, rpx_h) != (px_w, px_h):
            layer = layer.resize((px_w, px_h), Image.BILINEAR)
        if opacity < 1.0:
            layer.putalpha(layer.getchannel("A").point(lambda a: int(a * opacity)))
        if base.mode != "RGB":
            base = base.convert("RGB")
        base.paste(layer, (0, 0), layer)
        return base
