import tempfile
from pathlib import Path

from cartotui.cache import TileCache


def _cache():
    return TileCache(
        url_template="https://example.invalid/{z}/{x}/{y}.png",
        cache_dir=Path(tempfile.mkdtemp()),
        user_agent="test",
        retries=0,
    )


def test_cached_only_skips_download():
    c = _cache()
    assert c.get_tile_exact(5, 1, 1, cached_only=True) is None
    assert c.get_tile_with_overzoom(5, 1, 1, cached_only=True) is None
    c.close()


def test_out_of_range_returns_none():
    c = _cache()
    assert c.get_tile_exact(2, 99, 99, cached_only=True) is None
    c.close()
