"""Built-in tile source registry.

A ``Source`` is a small descriptor that says where to fetch tiles from. Two
families:

  * Raster sources — `{z}/{x}/{y}.png` URLs that the standard ``TileCache``
    can fetch.
  * Vector sources — backed by ``VectorTileSource`` (Protomaps API, raw MVT,
    or PMTiles archives).

Pressing ``[K]`` in-app cycles through the registry; the source changes
without restarting and the new tiles flow into both the cache and the
vector pipeline.

Users can extend the registry via ``vector.custom_sources`` /
``network.custom_raster_sources`` in their config — the in-app cycler
appends those after the built-ins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

__all__ = ["Source", "BUILTIN_SOURCES", "build_source_list"]


@dataclass
class Source:
    """A named tile source that can be selected at runtime."""

    name: str                       # short label shown in status / toolbar
    description: str                # tooltip-ish longer text
    kind: str                       # "raster" | "vector"
    url_template: str               # for raster: PNG tile URL; for vector mvt_url
    vector_backend: Optional[str] = None  # protomaps_api | pmtiles_url | mvt_url
    pmtiles_url: str = ""
    needs_key: bool = False         # whether this source requires an API key
    attribution: str = ""           # human-readable attribution


# Built-in registry. The first source that doesn't need a key is the default.
BUILTIN_SOURCES: List[Source] = [
    # ---- Raster basemaps ----
    Source(
        name="OSM",
        description="OpenStreetMap standard",
        kind="raster",
        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors",
    ),
    Source(
        name="Topo",
        description="OpenTopoMap (terrain shading)",
        kind="raster",
        url_template="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap, SRTM | Map: © OpenTopoMap (CC-BY-SA)",
    ),
    Source(
        name="Humanitarian",
        description="OSM Humanitarian (HOT) — high-contrast roads",
        kind="raster",
        url_template="https://tile-a.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap, HOT",
    ),
    Source(
        name="Positron",
        description="CARTO Positron (light, minimal — Google-Maps-ish)",
        kind="raster",
        url_template="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap, © CARTO",
    ),
    Source(
        name="DarkMatter",
        description="CARTO Dark Matter (dark with bright roads)",
        kind="raster",
        url_template="https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap, © CARTO",
    ),
    Source(
        name="Voyager",
        description="CARTO Voyager (warm, balanced)",
        kind="raster",
        url_template="https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap, © CARTO",
    ),

    # ---- Vector ----
    Source(
        name="Protomaps",
        description="Protomaps hosted vector basemap (needs API key)",
        kind="vector",
        url_template="https://api.protomaps.com/tiles/v4/{z}/{x}/{y}.mvt",
        vector_backend="protomaps_api",
        needs_key=True,
        attribution="© OpenStreetMap, © Protomaps",
    ),
]


def build_source_list(cfg: dict) -> List[Source]:
    """Compose the runtime source list: built-ins + any user customs from config.

    ``cfg`` is the top-level Config dict. We look in ``vector.custom_sources``
    (a list of Source-shaped dicts) and append them after the built-ins.
    """
    sources = list(BUILTIN_SOURCES)
    custom = []
    if isinstance(cfg, dict):
        custom = (cfg.get("vector", {}) or {}).get("custom_sources") or []
    for entry in custom:
        if not isinstance(entry, dict):
            continue
        try:
            sources.append(Source(
                name=str(entry.get("name") or "Custom"),
                description=str(entry.get("description") or ""),
                kind=str(entry.get("kind") or "raster"),
                url_template=str(entry.get("url_template") or ""),
                vector_backend=entry.get("vector_backend"),
                pmtiles_url=str(entry.get("pmtiles_url") or ""),
                needs_key=bool(entry.get("needs_key", False)),
                attribution=str(entry.get("attribution") or ""),
            ))
        except Exception:
            continue
    return sources
