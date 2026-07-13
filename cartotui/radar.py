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
        self._cache = {}
        self._lru = []
        self._lock = threading.Lock()

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

    def _tile_coords(self, lat, lon, z, px_w, px_h):
        rz = min(int(z), RADAR_MAX_Z)
        scale = 2 ** (z - rz)
        tp = self.tile_size
        rpx_w = max(1, px_w // scale)
        rpx_h = max(1, px_h // scale)
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

    def prefetch_viewport(self, lat, lon, z, px_w, px_h, color=4, smooth=1, snow=1):
        frames = list(self._frames_all)
        if not frames:
            return
        rz, coords = self._tile_coords(lat, lon, z, px_w, px_h)
        tasks = [(f.get("time"), f.get("path"), x, y) for f in frames for (x, y) in coords]

        def work():
            from concurrent.futures import ThreadPoolExecutor
            try:
                with ThreadPoolExecutor(max_workers=6) as ex:
                    futs = [ex.submit(self._tile_for, t, p, rz, x, y, color, smooth, snow)
                            for (t, p, x, y) in tasks]
                    for fu in futs:
                        fu.result()
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _maybe_prefetch(self, lat, lon, z, px_w, px_h, color, smooth, snow):
        frames = self._frames_all
        if not frames:
            return
        sig = (round(lat, 2), round(lon, 2), int(z), len(frames),
               frames[0].get("time"), frames[-1].get("time"))
        if sig == self._prefetch_sig:
            return
        self._prefetch_sig = sig
        self.prefetch_viewport(lat, lon, z, px_w, px_h, color, smooth, snow)

    def composite_onto(self, base: Image.Image, lat: float, lon: float, z: int,
                       px_w: int, px_h: int, opacity: float = 0.65, color: int = 4,
                       smooth: int = 1, snow: int = 1, which: str = "latest") -> Image.Image:
        self.refresh_frames()
        frame = self._active_frame(which)
        if not frame:
            return base
        self._frame_time = frame.get("time")
        self._frame_path = frame.get("path")
        if self.animate:
            self._maybe_prefetch(lat, lon, z, px_w, px_h, color, smooth, snow)

        tp = self.tile_size
        rz = min(int(z), RADAR_MAX_Z)
        scale = 2 ** (z - rz)
        rpx_w = max(1, px_w // scale)
        rpx_h = max(1, px_h // scale)

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
                tile = self._get_tile(rz, tx % n, ty, color, smooth, snow)
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
            alpha = layer.split()[3].point(lambda a: int(a * opacity))
            layer.putalpha(alpha)
        out = Image.alpha_composite(base.convert("RGBA"), layer)
        return out.convert("RGB")
