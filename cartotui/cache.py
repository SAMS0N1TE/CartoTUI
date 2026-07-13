
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Set, Tuple

import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("cartotui.cache")

__all__ = ["TileCache"]

def _style_dir(base_dir: Path, url_template: str) -> Path:
    h = hashlib.sha1(url_template.encode("utf-8")).hexdigest()[:10]
    return base_dir / h

class TileCache:

    def __init__(
        self,
        url_template: str,
        cache_dir: Path,
        user_agent: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        retries: int = 3,
        parallel_downloads: int = 8,
    ) -> None:
        self.url_template = url_template
        self.cache_dir = cache_dir
        self.root_dir = _style_dir(Path(cache_dir), url_template)
        self.root_dir.mkdir(parents=True, exist_ok=True)

        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=parallel_downloads,
            pool_maxsize=parallel_downloads,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self._disk_lock = threading.Lock()
        self._inflight: Set[Tuple[int, int, int]] = set()
        self._inflight_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=parallel_downloads,
            thread_name_prefix="tile-fetch",
        )
        self._closed = False

    def _tile_path(self, z: int, x: int, y: int) -> Path:
        return self.root_dir / str(z) / str(x) / f"{y}.png"

    def _ensure_dir(self, p: Path) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)

    def get_tile_exact(self, z: int, x: int, y: int,
                       cached_only: bool = False) -> Optional[Image.Image]:
        n = 2 ** z
        if not (0 <= x < n and 0 <= y < n):
            return None

        p = self._tile_path(z, x, y)
        if p.exists():
            try:
                return Image.open(p).convert("RGB")
            except Exception as e:
                log.debug("Cached tile unreadable, re-fetching %s: %s", p, e)
                try:
                    p.unlink()
                except OSError:
                    pass

        if cached_only:
            return None
        return self._download(z, x, y)

    def get_tile_with_overzoom(
        self,
        z: int,
        x: int,
        y: int,
        overzoom_levels: int = 2,
        cached_only: bool = False,
    ) -> Optional[Image.Image]:
        img = self.get_tile_exact(z, x, y, cached_only=cached_only)
        if img is not None:
            return img

        for step in range(1, overzoom_levels + 1):
            parent_z = z - step
            if parent_z < 0:
                break
            factor = 2 ** step
            parent = self.get_tile_exact(parent_z, x // factor, y // factor,
                                         cached_only=cached_only)
            if parent is None:
                continue
            sub_w = parent.width // factor
            sub_h = parent.height // factor
            ox = (x % factor) * sub_w
            oy = (y % factor) * sub_h
            try:
                return (
                    parent.crop((ox, oy, ox + sub_w, oy + sub_h))
                    .resize((parent.width, parent.height), Image.LANCZOS)
                )
            except Exception as e:
                log.debug("Overzoom failed at z=%d step=%d: %s", z, step, e)
        return None

    def prefetch(self, tiles: Iterable[Tuple[int, int, int]]) -> List[Future]:
        if self._closed:
            return []
        futures: List[Future] = []
        for z, x, y in tiles:
            n = 2 ** z
            if not (0 <= x < n and 0 <= y < n):
                continue
            if self._tile_path(z, x, y).exists():
                continue
            with self._inflight_lock:
                if (z, x, y) in self._inflight:
                    continue
                self._inflight.add((z, x, y))
            futures.append(self._executor.submit(self._download_silent, z, x, y))
        return futures

    def _download(self, z: int, x: int, y: int) -> Optional[Image.Image]:
        url = self.url_template.format(z=z, x=x, y=y)
        try:
            r = self.session.get(url, timeout=(self.connect_timeout, self.read_timeout))
        except requests.RequestException as e:
            log.debug("HTTP error for %s: %s", url, e)
            return None
        if r.status_code != 200 or not r.content:
            log.debug("Bad tile response %s: %d", url, r.status_code)
            return None
        try:
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:
            log.debug("Decode failed for %s: %s", url, e)
            return None
        p = self._tile_path(z, x, y)
        with self._disk_lock:
            try:
                self._ensure_dir(p)
                img.save(p, "PNG", optimize=False)
            except OSError as e:
                log.debug("Write failed for %s: %s", p, e)
        return img

    def _download_silent(self, z: int, x: int, y: int) -> None:
        try:
            self._download(z, x, y)
        finally:
            with self._inflight_lock:
                self._inflight.discard((z, x, y))

    def prune(self, max_bytes: int, watermark: float = 0.85) -> int:
        try:
            files: List[Tuple[Path, int, float]] = []
            total = 0
            for root, _, names in os.walk(self.root_dir):
                for name in names:
                    if not name.endswith(".png"):
                        continue
                    path = Path(root) / name
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    total += st.st_size
                    files.append((path, st.st_size, st.st_mtime))
            if total <= max_bytes:
                return 0
            files.sort(key=lambda t: t[2])
            target = int(max_bytes * watermark)
            freed = 0
            for path, size, _mtime in files:
                if total <= target:
                    break
                try:
                    path.unlink()
                    total -= size
                    freed += size
                except OSError:
                    pass
            return freed
        except OSError as e:
            log.debug("Prune failed: %s", e)
            return 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.session.close()
        except Exception:
            pass
