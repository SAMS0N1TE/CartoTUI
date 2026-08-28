
from __future__ import annotations

import gzip
import logging
import math
import threading
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter

from cartotui.mvt_decoder import decode as _pure_decode

try:
    import mapbox_vector_tile
except ImportError:
    mapbox_vector_tile = None

try:
    from pmtiles import reader as pmtiles_reader
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
except ImportError:
    pmtiles_reader = None
    Compression = None
    TileType = None
    zxy_to_tileid = None

log = logging.getLogger("cartotui.vector")

__all__ = ["VectorTileSource", "VectorTile"]

# A decoded tile is 2.5 MB of Python objects for a median tile and 7.9 MB for a
# dense one, so the cache has to be capped by weight rather than tile count.
_DECODED_BUDGET_BYTES = 192 * 1024 * 1024
_DECODED_BYTES_PER_RAW = 80          # measured ratio, decoded : compressed

# Bounds how fast a pan can cover fresh ground: N workers move N/rtt tiles a
# second, and a pan that outruns them reaches tiles that have not landed.
_PREFETCH_WORKERS = 8

@dataclass
class VectorTile:

    z: int
    x: int
    y: int
    extent: int
    layers: Dict[str, dict]

class VectorTileSource:

    def __init__(
        self,
        config: dict,
        cache_dir: Path,
        user_agent: str,
    ) -> None:
        self.cfg = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent

        self._lock = threading.Lock()
        self._decoded: OrderedDict = OrderedDict()
        self._decoded_sizes: Dict[Tuple[int, int, int], int] = {}
        self._decoded_bytes = 0
        self._max_cached = 256       # a ceiling; the byte budget binds first
        self._prefetch_inflight: set = set()
        self._prefetch_lock = threading.Lock()

        # What depth this source actually has. Tile servers advertise nothing,
        # so it is learned from 404s: versatiles' OSM tiles stop at z14, and
        # asking it for z15 returns nothing and renders a black screen.
        self._zoom_lock = threading.Lock()
        self._zoom_ok: set = set()
        self._zoom_missing: Dict[int, int] = {}

        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        # Sized to the prefetch, plus headroom for the render worker, which
        # fetches on this session too.
        _pool = _PREFETCH_WORKERS + 4
        _adapter = HTTPAdapter(pool_connections=_pool, pool_maxsize=_pool)
        self._session.mount("https://", _adapter)
        self._session.mount("http://", _adapter)
        self._prefetch_pool_obj = None
        self._last_centre = None     # for the direction of travel

        self._pm_reader = None
        self._pm_header: Optional[dict] = None
        self._pm_url: Optional[str] = None
        self._pm_failed_url: Optional[str] = None

        self._closed = False

    def get_tile(self, z: int, x: int, y: int) -> Optional[VectorTile]:
        key = (z, x, y)
        with self._lock:
            cached = self._decoded.get(key)
            if cached is not None:
                self._decoded.move_to_end(key)      # most recently used
                return cached

        raw = self._load_raw_from_disk(z, x, y)
        if raw is None:
            raw = self._fetch_raw(z, x, y)
            if raw is None:
                return None
            self._save_raw_to_disk(z, x, y, raw)

        decoded = self._decode(raw)
        if decoded is None:
            return None
        tile = VectorTile(z=z, x=x, y=y, extent=4096, layers=decoded)

        with self._lock:
            self._decoded[key] = tile
            self._decoded.move_to_end(key)
            approx = len(raw) * _DECODED_BYTES_PER_RAW
            self._decoded_bytes += approx - self._decoded_sizes.get(key, 0)
            self._decoded_sizes[key] = approx
            self._evict_locked()
        return tile

    def _evict_locked(self) -> None:
        """Drop least-recently-used tiles until the cache fits its budget."""
        while self._decoded and (self._decoded_bytes > _DECODED_BUDGET_BYTES
                                 or len(self._decoded) > self._max_cached):
            old_key, _ = self._decoded.popitem(last=False)
            self._decoded_bytes -= self._decoded_sizes.pop(old_key, 0)
        if not self._decoded:
            self._decoded_bytes = 0

    _MISSES_BEFORE_CAPPING = 3

    def _note_zoom(self, z: int, status: int) -> None:
        with self._zoom_lock:
            if status == 200:
                self._zoom_ok.add(z)
                self._zoom_missing.pop(z, None)
            elif status == 404:
                self._zoom_missing[z] = self._zoom_missing.get(z, 0) + 1

    def max_fetch_zoom(self, z: int) -> int:
        """The deepest zoom at or below `z` worth asking this source for.

        Above a source's real depth every tile 404s and the frame comes out
        empty. Clamping here lets the renderer scale the parent tiles up
        instead -- blurrier, but a map rather than a black screen.

        `vector.max_zoom` pins it explicitly; otherwise it is learned, stepping
        down one level per frame until it lands on a zoom that answers.
        """
        try:
            cap = int(self.cfg.get("max_zoom") or 0)
        except (TypeError, ValueError):
            cap = 0
        if cap <= 0 and self._pm_header:
            cap = int(self._pm_header.get("max_zoom") or 0)
        if cap > 0:
            return max(0, min(z, cap))
        with self._zoom_lock:
            # A tile pyramid is contiguous, so the shallowest zoom known to be
            # empty bounds every zoom below it too. Without that, learning walks
            # down one level per frame and each step shows a blank frame.
            dead = [zz for zz, misses in self._zoom_missing.items()
                    if misses >= self._MISSES_BEFORE_CAPPING and zz not in self._zoom_ok]
            if not dead:
                return int(z)
            return max(0, min(int(z), min(dead) - 1))

    def get_raw(self, z: int, x: int, y: int, cached_only: bool = False) -> Optional[bytes]:
        raw = self._load_raw_from_disk(z, x, y)
        if raw is not None:
            return raw
        if cached_only:
            return None
        raw = self._fetch_raw(z, x, y)
        if raw is not None:
            self._save_raw_to_disk(z, x, y, raw)
        return raw

    def _covering_tiles(self, lat, lon, z, px_w, px_h, tile_px=256, ring=0,
                        lead=(0, 0)):
        """The tiles the viewport touches, widened by `ring` on the leading edges.

        `lead` is the direction of travel in tile units, each component -1, 0 or
        +1. A ring is only useful ahead of the view: spent behind, it competes
        with the on-screen tiles for the same connections and costs more than it
        saves. A stationary axis widens both ways.
        """
        from cartotui.geodesy import latlon_to_tile_xy
        n = 1 << z
        xt, yt = latlon_to_tile_xy(lat, lon, z)
        cx = xt * tile_px
        cy = yt * tile_px
        ring = max(0, int(ring))
        lx, ly = lead
        if lx or ly:
            x_lo, x_hi = (ring if lx < 0 else 0), (ring if lx > 0 else 0)
            y_lo, y_hi = (ring if ly < 0 else 0), (ring if ly > 0 else 0)
        else:
            x_lo = x_hi = y_lo = y_hi = ring
        tx0 = int(math.floor((cx - px_w / 2.0) / tile_px)) - x_lo
        tx1 = int(math.floor((cx + px_w / 2.0) / tile_px)) + x_hi
        ty0 = int(math.floor((cy - px_h / 2.0) / tile_px)) - y_lo
        ty1 = int(math.floor((cy + px_h / 2.0) / tile_px)) + y_hi
        out = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if 0 <= tx < n and 0 <= ty < n:
                    out.append((z, tx, ty))
        return out

    def prefetch_viewport(self, lat, lon, z, px_w, px_h, ring: int = 1) -> None:
        """Get the viewport's tiles, and a ring ahead of them, onto disk.

        Raw bytes on disk are what the base map needs: the libcarto backend
        reads `get_raw`, and during a pan it passes `cached_only=True`, so a
        tile that has not landed is drawn as nothing. Only the pure-Python
        engine and the label overlays read the decoded cache.

        Do not decode here. Decode is ~18 ms of pure Python a tile and holds the
        GIL, and the base map never reads the result, so it would starve the
        render worker and delay the disk writes a pan is waiting on.
        """
        if self._closed:
            return
        try:
            lead = self._note_travel(lat, lon, z)
            core = self._covering_tiles(lat, lon, z, px_w, px_h)
            outer = (self._covering_tiles(lat, lon, z, px_w, px_h,
                                          ring=ring, lead=lead)
                     if ring else core)
        except Exception:
            return
        # On-screen tiles first: `_covering_tiles` walks from the top-left, so
        # submitting it as it comes would fetch the margin before the view.
        on_screen = set(core)
        ordered = list(core) + [t for t in outer if t not in on_screen]

        with self._prefetch_lock:
            missing = [
                t for t in ordered
                if t not in self._prefetch_inflight and not self._disk_path(*t).exists()
            ]
            if not missing:
                return
            for t in missing:
                self._prefetch_inflight.add(t)

        pool = self._prefetch_pool()
        for t in missing:
            try:
                pool.submit(self._prefetch_one, t)
            except RuntimeError:            # pool shut down under us
                with self._prefetch_lock:
                    self._prefetch_inflight.discard(t)

    def _note_travel(self, lat, lon, z):
        """Which way the view is moving, in tile units, as (-1|0|+1, -1|0|+1).

        Taken from the previous centre so callers need not thread it through. A
        zoom change or goto reads as stationary: no direction to lead in.
        """
        from cartotui.geodesy import latlon_to_tile_xy
        try:
            xt, yt = latlon_to_tile_xy(lat, lon, z)
        except Exception:
            return (0, 0)
        prev = self._last_centre
        self._last_centre = (z, xt, yt)
        if prev is None or prev[0] != z:
            return (0, 0)
        dx, dy = xt - prev[1], yt - prev[2]
        eps = 0.02                      # a fiftieth of a tile: real motion, not jitter
        return (1 if dx > eps else (-1 if dx < -eps else 0),
                1 if dy > eps else (-1 if dy < -eps else 0))

    def _prefetch_pool(self):
        """One executor for the life of the source, shared by every batch."""
        if self._prefetch_pool_obj is None:
            with self._prefetch_lock:
                if self._prefetch_pool_obj is None:
                    from concurrent.futures import ThreadPoolExecutor
                    self._prefetch_pool_obj = ThreadPoolExecutor(
                        max_workers=_PREFETCH_WORKERS,
                        thread_name_prefix="mvt-prefetch")
        return self._prefetch_pool_obj

    def _prefetch_one(self, t) -> None:
        try:
            self.get_raw(*t)
        except Exception:
            pass
        finally:
            with self._prefetch_lock:
                self._prefetch_inflight.discard(t)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        pool, self._prefetch_pool_obj = self._prefetch_pool_obj, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        try:
            self._session.close()
        except Exception:
            pass

    def _disk_path(self, z: int, x: int, y: int) -> Path:
        return self.cache_dir / self._source_namespace() / str(z) / str(x) / f"{y}.mvt"

    def _source_namespace(self) -> str:
        src = self.cfg.get("source", "pmtiles_url")
        if src == "pmtiles_url":
            url = self.cfg.get("pmtiles_url", "")
            return "pm_" + _short_hash(url)
        if src == "protomaps_api":
            return "papi_" + _short_hash(self.cfg.get("protomaps_api_key", ""))
        return "mvt_" + _short_hash(self.cfg.get("mvt_url", ""))

    def _load_raw_from_disk(self, z: int, x: int, y: int) -> Optional[bytes]:
        p = self._disk_path(z, x, y)
        if not p.exists():
            return None
        try:
            return p.read_bytes()
        except OSError:
            return None

    def _save_raw_to_disk(self, z: int, x: int, y: int, raw: bytes) -> None:
        p = self._disk_path(z, x, y)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        except OSError as e:
            log.debug("Failed to cache MVT %d/%d/%d: %s", z, x, y, e)

    def _fetch_raw(self, z: int, x: int, y: int) -> Optional[bytes]:
        src = self.cfg.get("source", "pmtiles_url")
        if src == "pmtiles_url":
            return self._fetch_pmtiles(z, x, y)
        if src == "protomaps_api":
            return self._fetch_protomaps_api(z, x, y)
        if src == "mvt_url":
            return self._fetch_mvt_url(z, x, y)
        log.warning("Unknown vector source: %s", src)
        return None

    def _fetch_protomaps_api(self, z: int, x: int, y: int) -> Optional[bytes]:
        url_tmpl = self.cfg.get("protomaps_api_url",
                                "https://api.protomaps.com/tiles/v4/{z}/{x}/{y}.mvt")
        key = self.cfg.get("protomaps_api_key", "")
        if not key:
            log.warning("protomaps_api selected but no protomaps_api_key set")
            return None
        url = url_tmpl.format(z=z, x=x, y=y) + f"?key={key}"
        return self._http_get(url, on_status=lambda code: self._note_zoom(z, code))

    def _fetch_mvt_url(self, z: int, x: int, y: int) -> Optional[bytes]:
        url_tmpl = self.cfg.get("mvt_url", "")
        if not url_tmpl:
            return None
        return self._http_get(url_tmpl.format(z=z, x=x, y=y),
                              on_status=lambda code: self._note_zoom(z, code))

    def _http_get(self, url: str, on_status=None) -> Optional[bytes]:
        with self._lock:
            if not getattr(self, "_logged_first_url", False):
                self._logged_first_url = True
                log.info("vector source first request: %s", _redact_key(url))

        headers = {
            "Accept": "application/x-protobuf, application/vnd.mapbox-vector-tile, */*",
            "Origin": "http://localhost",
            "Referer": "http://localhost/",
        }
        try:
            r = self._session.get(url, timeout=(5.0, 15.0), headers=headers)
        except requests.RequestException as e:
            self._log_failure_once(url, f"network error: {e.__class__.__name__}: {e}")
            return None
        if on_status is not None:
            on_status(r.status_code)
        if r.status_code == 404:
            log.debug("404 for %s", _redact_key(url))
            return None
        if r.status_code != 200:
            try:
                body = r.text[:200]
            except Exception:
                body = "(unreadable body)"
            self._log_failure_once(
                url, f"HTTP {r.status_code}: {body}",
            )
            return None
        if not r.content:
            self._log_failure_once(url, "200 OK but empty body")
            return None
        return r.content

    def _log_failure_once(self, url: str, msg: str) -> None:
        import re
        canon = re.sub(r"/\d+/\d+/\d+\.", "/{z}/{x}/{y}.", url)
        canon = _redact_key(canon)
        sig = (canon, msg)
        with self._lock:
            if not hasattr(self, "_logged_failures"):
                self._logged_failures = set()
            if sig in self._logged_failures:
                return
            self._logged_failures.add(sig)
        log.warning("vector tile fetch failed: %s — %s", canon, msg)

    def _ensure_pmtiles(self) -> bool:
        if pmtiles_reader is None:
            log.warning("pmtiles package not installed")
            return False
        url = self.cfg.get("pmtiles_url", "")
        if not url:
            log.warning("pmtiles_url not configured")
            return False
        if self._pm_reader is not None and self._pm_url == url:
            return True
        if self._pm_failed_url == url:
            return False

        session = self._session

        def get_bytes(offset: int, length: int) -> bytes:
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            r = session.get(url, headers=headers, timeout=(5.0, 30.0))
            if r.status_code not in (200, 206):
                raise RuntimeError(f"PMTiles range request failed: HTTP {r.status_code}")
            return r.content

        try:
            self._pm_reader = pmtiles_reader.Reader(get_bytes)
            self._pm_header = self._pm_reader.header()
            self._pm_url = url
            self._pm_failed_url = None
            tt = self._pm_header.get("tile_type")
            log.info("PMTiles opened: %s (%s tiles)", url, tt)
            return True
        except Exception as e:
            log.warning(
                "Failed to open PMTiles %s: %s "
                "(suppressing further retries this run; "
                "switch vector.source to 'protomaps_api' or change "
                "vector.pmtiles_url to a working archive)", url, e,
            )
            self._pm_reader = None
            self._pm_header = None
            self._pm_url = None
            self._pm_failed_url = url
            return False

    def _fetch_pmtiles(self, z: int, x: int, y: int) -> Optional[bytes]:
        if not self._ensure_pmtiles():
            return None
        try:
            raw = self._pm_reader.get(z, x, y)
        except Exception as e:
            log.debug("PMTiles get %d/%d/%d failed: %s", z, x, y, e)
            return None
        if raw is None or len(raw) == 0:
            return None
        comp = self._pm_header.get("tile_compression") if self._pm_header else None
        try:
            if Compression and comp == Compression.GZIP:
                raw = gzip.decompress(raw)
            elif Compression and comp == Compression.BROTLI:
                try:
                    import brotli
                    raw = brotli.decompress(raw)
                except ImportError:
                    log.warning("PMTiles uses brotli but brotli pkg is not installed")
                    return None
        except Exception as e:
            log.debug("PMTiles decompression failed: %s", e)
            return None
        return raw

    @staticmethod
    def _decompress_if_needed(raw: bytes) -> bytes:
        if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
            try:
                return gzip.decompress(raw)
            except Exception:
                return raw
        if len(raw) >= 2 and raw[0] == 0x78:
            try:
                return zlib.decompress(raw)
            except Exception:
                return raw
        return raw

    def _decode(self, raw: bytes) -> Optional[Dict[str, dict]]:
        raw = self._decompress_if_needed(raw)
        try:
            decoded = _pure_decode(raw, y_coord_down=True)
            if decoded:
                return decoded
        except Exception as e:
            log.debug("pure-python MVT decode failed: %s", e)

        if mapbox_vector_tile is None:
            log.warning(
                "MVT decode failed and mapbox-vector-tile not installed as "
                "fallback. Tile may be malformed or use unsupported features."
            )
            return None
        try:
            return mapbox_vector_tile.decode(
                raw, default_options={"y_coord_down": True}
            )
        except Exception as e:
            log.warning("MVT decode failed (both decoders): %s", e)
            return None

def _short_hash(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]

def _redact_key(url: str) -> str:
    import re

    def _sub(m):
        val = m.group(2)
        return m.group(1) + (val[:2] + "…" + val[-2:] if len(val) > 6 else "***")
    return re.sub(r"([?&]key=)([^&\s]+)", _sub, url)
