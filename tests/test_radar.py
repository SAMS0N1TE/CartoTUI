from PIL import Image

from cartotui.radar import RADAR_MAX_Z, RadarSource, _is_precip_tile


def _stub():
    rs = RadarSource()
    rs.refresh_frames = lambda *a, **k: None
    rs._host, rs._frame_path, rs._frame_time = "x", "/p", 1000
    rs._past = [{"time": 1000, "path": "/p"}]
    return rs


def test_precip_detection():
    colored = Image.new("RGBA", (16, 16), (0, 128, 255, 200))
    gray = Image.new("RGBA", (16, 16), (80, 80, 80, 200))
    transparent = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    assert _is_precip_tile(colored) is True
    assert _is_precip_tile(gray) is False
    assert _is_precip_tile(transparent) is False


def test_composite_blends_precip():
    rs = _stub()
    rs._get_tile = lambda *a, **k: Image.new("RGBA", (256, 256), (255, 0, 0, 255))
    out = rs.composite_onto(Image.new("RGB", (200, 200), (0, 0, 0)),
                            43.2, -71.5, 8, 200, 200, opacity=0.5, which="latest")
    assert out.size == (200, 200)
    assert out.getpixel((100, 100))[0] > 100


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
