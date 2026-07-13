
from __future__ import annotations

import gzip
import logging
import math
import threading
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

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
        self._decoded: Dict[Tuple[int, int, int], VectorTile] = {}
        self._max_cached = 256
        self._prefetch_inflight: set = set()
        self._prefetch_lock = threading.Lock()

        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent

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
            if len(self._decoded) >= self._max_cached:
                drop = next(iter(self._decoded))
                self._decoded.pop(drop, None)
            self._decoded[key] = tile
        return tile

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

    def _covering_tiles(self, lat, lon, z, px_w, px_h, tile_px=256):
        from cartotui.geodesy import latlon_to_tile_xy
        n = 1 << z
        xt, yt = latlon_to_tile_xy(lat, lon, z)
        cx = xt * tile_px
        cy = yt * tile_px
        tx0 = int(math.floor((cx - px_w / 2.0) / tile_px))
        tx1 = int(math.floor((cx + px_w / 2.0) / tile_px))
        ty0 = int(math.floor((cy - px_h / 2.0) / tile_px))
        ty1 = int(math.floor((cy + px_h / 2.0) / tile_px))
        out = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if 0 <= tx < n and 0 <= ty < n:
                    out.append((z, tx, ty))
        return out

    def prefetch_viewport(self, lat, lon, z, px_w, px_h) -> None:
        try:
            tiles = self._covering_tiles(lat, lon, z, px_w, px_h)
        except Exception:
            return
        with self._prefetch_lock:
            missing = [
                t for t in tiles
                if t not in self._prefetch_inflight and not self._disk_path(*t).exists()
            ]
            if not missing:
                return
            for t in missing:
                self._prefetch_inflight.add(t)

        def work():
            from concurrent.futures import ThreadPoolExecutor
            try:
                with ThreadPoolExecutor(max_workers=min(6, len(missing))) as ex:
                    list(ex.map(lambda t: self.get_raw(*t), missing))
            except Exception:
                pass
            finally:
                with self._prefetch_lock:
                    for t in missing:
                        self._prefetch_inflight.discard(t)

        threading.Thread(target=work, daemon=True, name="mvt-prefetch").start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
        return self._http_get(url)

    def _fetch_mvt_url(self, z: int, x: int, y: int) -> Optional[bytes]:
        url_tmpl = self.cfg.get("mvt_url", "")
        if not url_tmpl:
            return None
        return self._http_get(url_tmpl.format(z=z, x=x, y=y))

    def _http_get(self, url: str) -> Optional[bytes]:
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
