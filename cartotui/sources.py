
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

__all__ = ["Source", "BUILTIN_SOURCES", "build_source_list"]

@dataclass
class Source:

    name: str
    description: str
    kind: str
    url_template: str
    vector_backend: Optional[str] = None
    pmtiles_url: str = ""
    needs_key: bool = False
    attribution: str = ""

BUILTIN_SOURCES: List[Source] = [
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
