import pytest

from cartotui.mvt_decoder import decode
from cartotui.vector_source import VectorTileSource


def field(tag, value):
    assert len(value) < 128
    return bytes([tag, len(value)]) + value


def tile():
    # Layer names may appear after features/extent, not just first.
    return b"".join(
        field(26, b"\x28\x80\x20" + field(10, name))
        for name in (b"buildings", b"place", b"water", b"boundary")
    )


def test_selective_decode_matches_full_subset_and_empty_result():
    full = decode(tile())
    assert decode(tile(), layer_names={"place", "boundary"}) == {
        k: v for k, v in full.items() if k in {"place", "boundary"}
    }
    assert decode(tile(), layer_names={"missing"}) == {}


@pytest.mark.parametrize(
    "raw", [b"\x1a\x7f\x00", b"\x1a\x80", b"\x80" * 15, field(26, b"\x0a\x7fname")]
)
def test_truncated_layer_rejected_without_hang(raw):
    with pytest.raises(ValueError):
        decode(raw, layer_names={"place"})


def test_overlay_cache_is_source_owned_and_weight_bounded(tmp_path, monkeypatch):
    import cartotui.vector_source as module

    source = VectorTileSource({}, tmp_path, "test")
    calls = []
    source.get_raw = lambda *args: calls.append(args) or tile()
    try:
        a = source.get_overlay_tile(1, 0, 0)
        assert source.get_overlay_tile(1, 0, 0) is a
        assert len(calls) == 1
        assert not source._decoded  # no full tile allocations
        assert set(a.layers) == {"place", "boundary"}
        size = source._overlay_bytes
        monkeypatch.setattr(module, "_OVERLAY_BUDGET_BYTES", size)
        source.get_overlay_tile(1, 1, 0)
        assert len(source._overlay_cache) == 1
        assert source._overlay_bytes <= size
        other = VectorTileSource({}, tmp_path / "other", "test")
        other.get_raw = lambda *args: b""
        try:
            assert other.get_overlay_tile(1, 0, 0).layers == {}
        finally:
            other.close()
    finally:
        source.close()
