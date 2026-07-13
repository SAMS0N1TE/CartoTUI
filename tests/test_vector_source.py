import tempfile
from pathlib import Path

from cartotui.vector_source import VectorTileSource


def _src():
    cfg = {
        "source": "mvt_url",
        "mvt_url": "https://example.invalid/{z}/{x}/{y}",
        "pmtiles_url": "",
        "protomaps_api_key": "",
        "protomaps_api_url": "",
        "style": "auto",
    }
    return VectorTileSource(cfg, cache_dir=Path(tempfile.mkdtemp()) / "v", user_agent="test")


def test_get_raw_cached_only_skips_network():
    vs = _src()
    calls = []
    vs._fetch_raw = lambda z, x, y: calls.append((z, x, y)) or None
    assert vs.get_raw(14, 1, 2, cached_only=True) is None
    assert calls == []  # never touched the network


def test_get_raw_uses_disk_before_network():
    vs = _src()
    vs._save_raw_to_disk(14, 1, 2, b"tiledata")
    hit = []
    vs._fetch_raw = lambda z, x, y: hit.append((z, x, y)) or b"net"
    assert vs.get_raw(14, 1, 2) == b"tiledata"
    assert vs.get_raw(14, 1, 2, cached_only=True) == b"tiledata"
    assert hit == []  # disk hit, no fetch


def test_get_raw_fetches_and_caches():
    vs = _src()
    vs._fetch_raw = lambda z, x, y: b"fresh"
    assert vs.get_raw(14, 5, 6) == b"fresh"
    assert vs._disk_path(14, 5, 6).exists()  # saved for next time


def test_covering_tiles_spans_viewport():
    vs = _src()
    tiles = vs._covering_tiles(43.2081, -71.5376, 14, 720, 600)
    assert tiles
    assert all(t[0] == 14 for t in tiles)
    assert len(tiles) == len(set(tiles))  # no duplicates
