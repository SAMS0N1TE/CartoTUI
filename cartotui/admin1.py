
from __future__ import annotations

import gzip
import json
import logging
import os
from functools import lru_cache
from typing import Sequence, Tuple

log = logging.getLogger("cartotui.admin1")

_PATH = os.path.join(os.path.dirname(__file__), "data", "admin1_lines.geojson.gz")

TILE_ADMIN1_MIN_Z = 7

Admin1Line = Tuple[float, Tuple[Tuple[float, float], ...]]

@lru_cache(maxsize=1)
def admin1_lines() -> Sequence[Admin1Line]:
    try:
        with gzip.open(_PATH, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        log.warning("admin-1 boundary data unavailable (%s)", e)
        return ()

    out = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        try:
            min_zoom = float(props.get("mz") or 0)
        except (TypeError, ValueError):
            min_zoom = 0.0
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if gtype == "LineString":
            lines = [coords]
        elif gtype == "MultiLineString":
            lines = coords or []
        else:
            continue
        for line in lines:
            if not line or len(line) < 2:
                continue
            try:
                pts = tuple((float(p[0]), float(p[1])) for p in line)
            except (TypeError, ValueError, IndexError):
                continue
            out.append((min_zoom, pts))
    return tuple(out)
