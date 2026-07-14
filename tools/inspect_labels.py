"""Print the layers and place/admin label kinds a vector source ships for a view."""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cartotui.config import Config                      # noqa: E402
from cartotui.geodesy import latlon_to_tile_xy          # noqa: E402
from cartotui.vector_source import VectorTileSource     # noqa: E402

_PLACE_LAYERS = {"places", "place_labels", "place"}
_BOUNDARY_LAYERS = {"boundaries", "boundary", "admin", "admin_boundaries"}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--mvt-url")
    p.add_argument("--pmtiles-url")
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("--zoom", type=int)
    p.add_argument("--radius", type=int, default=2, help="tiles around centre")
    args = p.parse_args(argv)

    cfg = Config.load(args.config)
    vcfg = dict(cfg["vector"])
    if args.mvt_url:
        vcfg["source"] = "mvt_url"
        vcfg["mvt_url"] = args.mvt_url
    elif args.pmtiles_url:
        vcfg["source"] = "pmtiles_url"
        vcfg["pmtiles_url"] = args.pmtiles_url

    lat = args.lat if args.lat is not None else float(cfg["map"]["center_lat"])
    lon = args.lon if args.lon is not None else float(cfg["map"]["center_lon"])
    zoom = args.zoom if args.zoom is not None else int(cfg["map"]["zoom"])
    fetch_z = min(max(zoom, 0), 15)

    print(f"source : {vcfg['source']}")
    print(f"url    : {vcfg.get('mvt_url') or vcfg.get('pmtiles_url') or vcfg.get('protomaps_api_url')}")
    print(f"view   : lat={lat} lon={lon} zoom={zoom} (fetch z={fetch_z})")
    print("-" * 64)

    src = VectorTileSource(
        vcfg,
        cache_dir=Path(cfg["cache"]["dir"]) / "vector",
        user_agent=cfg["network"]["user_agent"],
    )

    cx, cy = latlon_to_tile_xy(lat, lon, fetch_z)
    tx0, ty0 = int(cx), int(cy)
    n = 2 ** fetch_z

    layer_features: Counter = Counter()
    place_kinds: Counter = Counter()
    place_examples: dict = defaultdict(list)
    admin_levels: Counter = Counter()
    tiles_ok = 0

    for dx in range(-args.radius, args.radius + 1):
        for dy in range(-args.radius, args.radius + 1):
            tx, ty = (tx0 + dx) % n, ty0 + dy
            if not (0 <= ty < n):
                continue
            try:
                tile = src.get_tile(fetch_z, tx, ty)
            except Exception as e:
                print(f"  tile {fetch_z}/{tx}/{ty}: fetch error {e}")
                continue
            if tile is None:
                continue
            tiles_ok += 1
            for lname, layer in tile.layers.items():
                feats = layer.get("features", [])
                layer_features[lname] += len(feats)
                if lname in _PLACE_LAYERS:
                    for f in feats:
                        pr = f.get("properties") or {}
                        kind = str(pr.get("kind") or pr.get("class")
                                   or pr.get("pmap:kind") or "?").lower()
                        place_kinds[kind] += 1
                        nm = pr.get("name") or pr.get("name:en") or pr.get("name:latin")
                        if nm and len(place_examples[kind]) < 6:
                            place_examples[kind].append(str(nm))
                if lname in _BOUNDARY_LAYERS:
                    for f in feats:
                        pr = f.get("properties") or {}
                        lvl = pr.get("admin_level")
                        admin_levels[str(lvl)] += 1

    src.close()

    print(f"tiles fetched OK: {tiles_ok}")
    print()
    print("LAYERS (feature counts):")
    if not layer_features:
        print("  (none — source returned no tiles; check the URL/network)")
    for name, cnt in layer_features.most_common():
        tag = ""
        if name in _PLACE_LAYERS:
            tag = "  <-- place labels"
        elif name in _BOUNDARY_LAYERS:
            tag = "  <-- boundaries"
        print(f"  {name:24} {cnt:6d}{tag}")

    print()
    print("PLACE-LABEL kinds (what feeds city/state/country titles):")
    if not place_kinds:
        print("  (no place-label layer found under names:",
              ", ".join(sorted(_PLACE_LAYERS)), ")")
    for kind, cnt in place_kinds.most_common():
        ex = ", ".join(place_examples.get(kind, [])[:5])
        star = "  ***" if kind in ("country", "state", "region", "province") else ""
        print(f"  {kind:16} {cnt:5d}{star}   e.g. {ex}")

    if admin_levels:
        print()
        print("BOUNDARY admin_levels:", dict(admin_levels))

    print()
    have_cs = any(k in place_kinds for k in ("country", "state", "region", "province"))
    if have_cs:
        print("=> Country/state labels ARE present at this zoom.")
    else:
        print("=> No country/state label points in these tiles at this zoom.")
        print("   They likely live only in coarser (lower-zoom) tiles.")


if __name__ == "__main__":
    main()
