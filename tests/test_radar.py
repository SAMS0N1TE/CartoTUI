from PIL import Image

from cartotui.radar import RADAR_MAX_Z, RadarSource, _is_precip_tile


def _stub():
    rs = RadarSource()
    rs.refresh_frames = lambda *a, **k: None
    rs._prefetch = lambda *a, **k: None
    rs._host, rs._frame_path, rs._frame_time = "x", "/p", 1000
    rs._past = [{"time": 1000, "path": "/p"}]
    return rs


def _red_tile():
    return Image.new("RGBA", (256, 256), (255, 0, 0, 255))


def test_precip_detection():
    colored = Image.new("RGBA", (16, 16), (0, 128, 255, 200))
    gray = Image.new("RGBA", (16, 16), (80, 80, 80, 200))
    transparent = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    assert _is_precip_tile(colored) is True
    assert _is_precip_tile(gray) is False
    assert _is_precip_tile(transparent) is False


def test_build_layer_returns_a_standalone_rgba_layer():
    rs = _stub()
    rs._get_cached = lambda *a, **k: _red_tile()
    layer = rs.build_layer(43.2, -71.5, 8, 200, 200, opacity=0.5, which="latest")
    assert layer is not None
    assert layer.mode == "RGBA"
    assert layer.size == (200, 200)
    assert 100 < layer.getpixel((100, 100))[3] < 160


def test_build_layer_returns_none_when_nothing_cached():
    rs = _stub()
    rs._get_cached = lambda *a, **k: None
    assert rs.build_layer(43.2, -71.5, 8, 200, 200) is None


def test_composite_cached_only_draws_from_cache():
    rs = _stub()
    rs._get_cached = lambda *a, **k: _red_tile()
    out = rs.composite_onto(Image.new("RGB", (200, 200), (0, 0, 0)),
                            43.2, -71.5, 8, 200, 200, opacity=0.5, which="latest")
    assert out.size == (200, 200)
    assert out.getpixel((100, 100))[0] > 100


def test_composite_cached_only_skips_uncached_tiles():
    rs = _stub()
    rs._get_cached = lambda *a, **k: None
    base = Image.new("RGB", (200, 200), (7, 7, 7))
    out = rs.composite_onto(base, 43.2, -71.5, 8, 200, 200)
    assert out.getpixel((100, 100)) == (7, 7, 7)


def test_composite_sync_path_fetches_tiles():
    rs = _stub()
    rs._get_tile = lambda *a, **k: _red_tile()
    out = rs.composite_onto(Image.new("RGB", (200, 200), (0, 0, 0)),
                            43.2, -71.5, 8, 200, 200, opacity=0.5,
                            which="latest", cached_only=False)
    assert out.size == (200, 200)
    assert out.getpixel((100, 100))[0] > 100


def test_on_tiles_ready_fires_after_prefetch():
    rs = RadarSource()
    rs._host, rs._frame_time, rs._frame_path = "x", 1, "/p"
    rs._tile_for = lambda *a, **k: _red_tile()
    fired = []
    rs.on_tiles_ready = lambda: fired.append(True)
    frame = {"time": 1, "path": "/p"}
    rs._prefetch(43.2, -71.5, 5, 256, 256, 4, 1, 1, [frame])
    import time as _t
    for _ in range(50):
        if fired:
            break
        _t.sleep(0.02)
    assert fired == [True]


def test_composite_no_frame_returns_base():
    rs = RadarSource()
    rs.refresh_frames = lambda *a, **k: None
    base = Image.new("RGB", (64, 64), (1, 2, 3))
    assert rs.composite_onto(base, 0, 0, 5, 64, 64) is base


def test_overzoom_caps_at_max():
    rs = _stub()
    rz, coords = rs._tile_coords(43.2, -71.5, 14, 512, 512)
    assert rz == RADAR_MAX_Z
    assert len(coords) >= 1


def test_radar_plan_keeps_tile_count_small():
    rs = _stub()
    rz, coords = rs._tile_coords(43.72, -73.12, 5, 1400, 1400)
    assert rz < 5
    assert len(coords) <= 16


def test_inflight_balances_to_zero_after_prefetch():
    rs = RadarSource()
    rs._host, rs._frame_time, rs._frame_path = "x", 1, "/p"
    rs._tile_for = lambda *a, **k: _red_tile()
    assert rs.loading() == 0
    done = []
    rs.on_tiles_ready = lambda: done.append(True)
    rs._prefetch(43.2, -71.5, 5, 512, 512, 4, 1, 1, [{"time": 1, "path": "/p"}])
    import time as _t
    for _ in range(100):
        if done:
            break
        _t.sleep(0.02)
    assert done == [True]
    assert rs.loading() == 0


def test_animation_index_cycles():
    rs = RadarSource()
    rs._frames_all = [{"time": i, "path": f"/{i}"} for i in range(4)]
    rs.animate = True
    assert rs.frame_count() == 4
    rs.advance()
    assert rs.anim_index() == 1
    rs.advance(); rs.advance(); rs.advance()
    assert rs.anim_index() == 0
    assert rs._active_frame("latest")["path"] == "/0"


def test_latest_changed():
    rs = RadarSource()
    rs._past = [{"time": 100, "path": "/a"}]
    assert rs.latest_changed() is True
    assert rs.latest_changed() is False
    rs._past = [{"time": 200, "path": "/b"}]
    assert rs.latest_changed() is True


def test_refresh_interval_config_validated():
    from cartotui.config import _validate
    c = _validate({"overlays": {"radar": {"refresh_interval_s": 5}}})
    assert c["overlays"]["radar"]["refresh_interval_s"] == 15.0
    c = _validate({"overlays": {"radar": {"refresh_interval_s": 99999}}})
    assert c["overlays"]["radar"]["refresh_interval_s"] == 3600.0
    c = _validate({"overlays": {"radar": {}}})
    assert c["overlays"]["radar"]["refresh_interval_s"] == 120.0


def test_refresh_frames_respects_meta_ttl():
    import time
    rs = RadarSource()
    rs.meta_ttl_s = 1000.0
    rs._frame_path = "/p"
    rs._last_meta = time.monotonic()
    # Within TTL and not forced: returns early without any network attempt.
    rs.refresh_frames()
    assert rs._host is None


def test_fmt_interval():
    from cartotui.ui.widgets.radar_widget import _fmt_interval
    assert _fmt_interval(30) == "30s"
    assert _fmt_interval(60) == "1m"
    assert _fmt_interval(300) == "5m"
