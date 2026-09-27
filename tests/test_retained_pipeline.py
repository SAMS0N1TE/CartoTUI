import time

import pytest

from cartotui.rendering.libcarto_backend import _get_renderer, rasterise_view_libcarto
from cartotui.themes import theme_vector_style
from cartotui.ui.map_control import MapControl


def test_native_tile_cache_retries_misses_and_isolates_sources():
    try:
        native = _get_renderer()
    except RuntimeError:
        pytest.skip("native library unavailable")
    a, b = object(), object()
    key = (a, 1, 0, 0)
    native._store_tile(key, None)
    assert key not in native._tile_cache
    native._store_tile(key, b"first")
    native._store_tile((b, 1, 0, 0), b"second")
    assert bytes(native._tile_cache[key][0]) == b"first"
    assert bytes(native._tile_cache[(b, 1, 0, 0)][0]) == b"second"
    old = native._tile_bytes
    native._store_tile(key, b"replacement")
    assert native._tile_bytes == old + len(b"replacement") - len(b"first")
    assert native._tile_lru.count(key) == 1


def test_retained_view_invalidates_style_source_and_tile_generation():
    class Source:
        def __init__(self):
            self.calls = 0

        def get_raw(self, *args, **kwargs):
            self.calls += 1
            # Valid empty MVT layer.
            return b"\x1a\x07\x0a\x05water"

    try:
        native = _get_renderer()
    except RuntimeError:
        pytest.skip("native library unavailable")
    source = Source()
    style = theme_vector_style("night", {})

    def render(s=source, st=style):
        return rasterise_view_libcarto(s, 0, 0, 1, 60, 60, style=st, lazy=True)

    a = render()
    assert a is not None
    assert render() is a
    changed_style = render(st=theme_vector_style("paper", {}))
    assert changed_style is not a
    other = Source()
    assert render(other) is not changed_style
    assert other.calls > 0
    a = render()
    native.tile_generation += 1
    assert render() is not a


def test_output_budget_coalesces_work_without_changing_quality():
    control = object.__new__(MapControl)

    class State:
        pass

    control.state = State()
    control.cfg = {"render": {"output_mbps": 10, "vector_scale": 6}}
    start = time.monotonic()
    control.note_output(0.002, 400000)
    assert 0.31 < control._next_render_at - start < 0.4
    assert control.cfg["render"]["vector_scale"] == 6
    assert control.state.last_output_bytes == 400000
