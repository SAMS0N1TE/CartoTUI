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


def test_prefetch_ring_leads_the_direction_of_travel():
    """A ring is only useful ahead of the view.

    Spent behind, it competes with the on-screen tiles for the same
    connections and at speed costs more than it saves.
    """
    vs = _src()
    base = vs._covering_tiles(43.02, -71.47, 12, 1400, 700)
    east = vs._covering_tiles(43.02, -71.47, 12, 1400, 700, ring=1, lead=(1, 0))
    still = vs._covering_tiles(43.02, -71.47, 12, 1400, 700, ring=1, lead=(0, 0))

    assert max(t[1] for t in east) == max(t[1] for t in base) + 1
    assert min(t[1] for t in east) == min(t[1] for t in base)
    assert {t[2] for t in east} == {t[2] for t in base}
    assert len(still) > len(east) > len(base)


def test_travel_direction_read_from_successive_centres():
    vs = _src()
    assert vs._note_travel(43.0, -71.5, 12) == (0, 0)      # nothing to compare
    assert vs._note_travel(43.0, -71.0, 12) == (1, 0)      # east
    assert vs._note_travel(42.5, -71.0, 12) == (0, 1)      # south, y grows down
    assert vs._note_travel(42.5, -71.0, 13) == (0, 0)      # zoom change is a jump


def test_prefetch_lands_raw_bytes_without_decoding():
    """The base map reads get_raw, so the prefetch must fill the disk.

    Decoding here would spend the pool on ~18 ms of GIL-held work per tile that
    the base map never reads, delaying the writes a pan is waiting on.
    """
    import time

    vs = _src()
    want = [(12, 100 + i, 200) for i in range(4)]
    vs._fetch_raw = lambda z, x, y: b"x" * 512
    vs._covering_tiles = lambda *a, **k: list(want)

    vs.prefetch_viewport(0.0, 0.0, 12, 480, 268, ring=0)
    for _ in range(200):
        with vs._prefetch_lock:
            if not vs._prefetch_inflight:
                break
        time.sleep(0.02)

    assert all(vs._disk_path(*t).exists() for t in want)
    assert all(vs.get_raw(*t, cached_only=True) for t in want)
    assert len(vs._decoded) == 0
    vs.close()


def test_decoded_cache_is_bounded_by_weight_and_evicts_lru():
    """A decoded tile is megabytes, so a flat count of 256 never really bound."""
    import cartotui.vector_source as vsm

    vs = _src()
    budget = vsm._DECODED_BUDGET_BYTES
    per = budget // 4
    raw_len = per // vsm._DECODED_BYTES_PER_RAW

    vs._decode = lambda raw: {"layer": {"features": []}}
    vs._fetch_raw = lambda z, x, y: b"x" * raw_len

    keep = (12, 0, 0)
    vs.get_tile(*keep)
    for i in range(1, 12):
        vs.get_tile(12, i, 0)
        vs.get_tile(*keep)                 # keep touching the first one

    assert vs._decoded_bytes <= budget
    assert vs._decoded_bytes == sum(vs._decoded_sizes.values())
    assert set(vs._decoded_sizes) == set(vs._decoded)
    assert keep in vs._decoded, "a tile touched every round must survive"
    vs.close()
