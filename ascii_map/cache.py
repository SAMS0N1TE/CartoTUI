#!/usr/bin/env python3
# ascii_map/cache.py
"""
Tile cache with style namespace and robust HTTP retry handling.

Derived and extended from original ascii_map.py TileCache implementation.
Features:
- SHA1-namespaced cache directories per style.
- Thread-safe disk read/write.
- Automatic retry using urllib3 Retry.
- Overzoom fallback for missing tiles.
- Optional pruning logic (to be integrated with config limits).
"""

from __future__ import annotations
import io, os, threading, time, hashlib
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image

# -------------------------
# Internal helpers
# -------------------------

def _style_cache_root(base_dir: Path, url_template: str) -> Path:
    """Generate deterministic cache subdir for a given style URL template."""
    h = hashlib.sha1(url_template.encode("utf-8")).hexdigest()[:10]
    return base_dir / h


# -------------------------
# TileCache
# -------------------------

class TileCache:
    """
    Persistent tile cache with HTTP fetch and overzoom support.
    Thread-safe. Safe for multi-reader use.
    """

    def __init__(
        self,
        url_template: str,
        cache_dir: Path,
        user_agent: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        retries: int = 3,
        pool_size: int = 8,
    ):
        self.url_template = url_template
        self.root_dir = _style_cache_root(cache_dir, url_template)
        self.root_dir.mkdir(parents=True, exist_ok=True)

        # HTTP session with retry
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
        adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self._lock = threading.Lock()

    # -------------
    # Path helpers
    # -------------

    def _tile_path(self, z: int, x: int, y: int) -> Path:
        """Return full path for tile image."""
        p = self.root_dir / str(z) / str(x)
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{y}.png"

    # -------------
    # Fetch logic
    # -------------

    def get_tile_exact(self, z: int, x: int, y: int, timeout: Optional[Tuple[float, float]] = None) -> Optional[Image.Image]:
        """
        Get an exact tile image from cache or network.
        Returns a Pillow Image or None if not found.
        """
        n = 2 ** z
        if not (0 <= x < n and 0 <= y < n):
            return None

        p = self._tile_path(z, x, y)
        if p.exists():
            try:
                with self._lock:
                    return Image.open(p).convert("RGB")
            except Exception:
                try:
                    p.unlink()
                except Exception:
                    pass

        url = self.url_template.format(z=z, x=x, y=y)
        try:
            r = self.session.get(url, timeout=timeout or (5.0, 10.0))
            if r.status_code == 200 and r.content:
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                with self._lock:
                    img.save(p, "PNG")
                return img
        except Exception:
            pass
        return None

    # ----------------------
    # Overzoom fetch logic
    # ----------------------

    def get_tile_with_overzoom(self, z: int, x: int, y: int, overzoom_levels: int = 2) -> Optional[Image.Image]:
        """
        Try to fetch a tile. If not present, attempt overzoom from parent tiles.
        overzoom_levels defines how far up we can look.
        """
        img = self.get_tile_exact(z, x, y)
        if img is not None:
            return img

        for step in range(1, overzoom_levels + 1):
            parent_z = z - step
            if parent_z < 0:
                break
            factor = 2 ** step
            px = x // factor
            py = y // factor
            parent = self.get_tile_exact(parent_z, px, py)
            if parent is None:
                continue
            # crop parent portion
            sub_w = parent.width // factor
            sub_h = parent.height // factor
            ox = (x % factor) * sub_w
            oy = (y % factor) * sub_h
            try:
                sub = parent.crop((ox, oy, ox + sub_w, oy + sub_h))
                sub = sub.resize((parent.width, parent.height), Image.LANCZOS)
                return sub
            except Exception:
                continue
        return None

    # ----------------------
    # Prune logic (optional)
    # ----------------------

    def prune(self, max_bytes: int, watermark: float = 0.85) -> None:
        """
        Delete oldest files if cache exceeds max_bytes.
        """
        try:
            total = 0
            files: List[Path] = []
            for root, _, names in os.walk(self.root_dir):
                for n in names:
                    if n.endswith(".png"):
                        p = Path(root) / n
                        total += p.stat().st_size
                        files.append(p)
            if total <= max_bytes:
                return
            files.sort(key=lambda p: p.stat().st_mtime)
            target = int(max_bytes * watermark)
            for f in files:
                if total <= target:
                    break
                try:
                    s = f.stat().st_size
                    f.unlink()
                    total -= s
                except Exception:
                    pass
        except Exception:
            pass
