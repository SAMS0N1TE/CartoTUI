"""PNG export: the terminal look, and the map with labels/aircraft drawn in."""
import numpy as np
import pytest
from PIL import Image

from cartotui.config import _validate
from cartotui.snapshot import find_mono_font, frame_to_png, save_frame_png


def _rows(w=40, h=12):
    """A frame with a flat background, some glyphs and a coloured label."""
    out = []
    for y in range(h):
        if y == 4:
            out.append([("fg:#ff8800", "▲ SWA221"), ("", " " * (w - 8))])
        else:
            out.append([("fg:#5ec46e", "▒" * w)])
    return out


def test_frame_to_png_renders_at_the_asked_cell_size():
    img = frame_to_png(_rows(), "green", cell_px=20)
    assert img.size == (40 * 12, 12 * 20)


def test_save_frame_png_scales_to_the_long_side(tmp_path):
    rows = _rows()
    sizes = []
    for want in (400, 800, 1600):
        p = tmp_path / f"s{want}.png"
        save_frame_png(rows, "green", str(p), long_side=want)
        sizes.append(Image.open(p).size)
    widths = [w for w, _h in sizes]
    assert widths == sorted(widths)
    for (w, h), want in zip(sizes, (400, 800, 1600)):
        assert max(w, h) <= want + 2


@pytest.mark.parametrize("theme", ["green", "amber", "paper", "night", "win31",
                                   "light", "dark", "ega", "retro", "hicon"])
def test_every_theme_exports(theme, tmp_path):
    p = tmp_path / f"{theme}.png"
    save_frame_png(_rows(), theme, str(p), long_side=300)
    assert Image.open(p).size[0] > 0


def test_export_carries_the_theme_colours():
    img = frame_to_png(_rows(), "green", cell_px=16)
    a = np.asarray(img.convert("RGB")).reshape(-1, 3)
    assert a[:, 1].mean() > a[:, 0].mean()


def test_export_survives_a_host_with_no_font(monkeypatch):
    """Boxes without fontconfig or any TTF still get an image, not a crash."""
    import cartotui.snapshot as S
    monkeypatch.setattr(S, "load_mono_font", lambda px: None)
    img = frame_to_png(_rows(), "green", cell_px=8)
    assert img.size[0] > 0


def test_find_mono_font_is_cached():
    a, b = find_mono_font(), find_mono_font()
    assert a == b


def test_empty_frame_does_not_raise():
    img = frame_to_png([], "green", cell_px=10)
    assert img.size[0] >= 1


def test_snapshot_config_defaults_and_validation():
    c = _validate({})["snapshot"]
    assert c["png_mode"] == "map"
    assert c["png_labels"] is False
    assert c["png_aircraft"] is False
    assert c["png_radar"] is True

    bad = _validate({"snapshot": {"png_mode": "hologram", "png_labels": "yes"}})["snapshot"]
    assert bad["png_mode"] == "map"
    assert bad["png_labels"] is True

    good = _validate({"snapshot": {"png_mode": "ascii"}})["snapshot"]
    assert good["png_mode"] == "ascii"


def test_label_and_marker_scaling_grows_with_the_export():
    """A 6x11 bitmap font is a speck on a 4096px PNG; both must scale."""
    from cartotui.geodesy import latlon_to_tile_xy
    from cartotui.raster_vector import _draw_aircraft
    from cartotui.themes import theme_vector_style
    from cartotui.traffic.aircraft import Aircraft
    from PIL import ImageDraw

    style = theme_vector_style("amber", {})
    W = H = 300
    tx, ty = latlon_to_tile_xy(43.2, -71.5, 9)
    wl, wt = tx * 256.0 - W / 2, ty * 256.0 - H / 2

    def ink(scale):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        _draw_aircraft(ImageDraw.Draw(img),
                       [Aircraft(icao="A1B2C3", callsign="SWA221", lat=43.2,
                                 lon=-71.5, altitude_ft=30000, track_deg=75)],
                       z=9, world_left_px=wl, world_top_px=wt,
                       width_px=W, height_px=H, style=style,
                       selected_icao="A1B2C3", scale=scale)
        return int((np.asarray(img.convert("L")) > 40).sum())

    inks = [ink(s) for s in (1.0, 2.0, 4.0)]
    assert inks == sorted(inks) and inks[-1] > inks[0] * 2, inks
