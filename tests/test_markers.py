"""Aircraft marker sizing: a terminal cell is fixed, so bigger means more cells."""
import pytest

from cartotui.themes import theme_vector_style
from cartotui.traffic.aircraft import Aircraft
from cartotui.ui.aircraft_overlay import (
    MARKER_SIZES,
    apply_aircraft_overlay,
    marker_span,
)

W, H = 30, 9


def _draw(size, track=90.0, label_mode="none"):
    rows = [[("", " " * W)] for _ in range(H)]
    acs = [Aircraft(icao="AAA111", callsign="SWA22", lat=43.20, lon=-71.50,
                    altitude_ft=30000, track_deg=track, ground_speed_kt=400)]
    hits = apply_aircraft_overlay(
        rows, acs, center_lat=43.20, center_lon=-71.50, z=8,
        term_w=W, term_h=H, canvas_px_w=W * 2, canvas_px_h=H * 4,
        style=theme_vector_style("night", {}),
        label_mode=label_mode, show_trails=False, show_legend=False,
        show_banner=False, dead_reckoning=False, predict_track=False,
        highlight_interesting=False, marker_style="arrow", marker_size=size,
    )
    y = hits[0][2]
    return "".join(t for _s, t in rows[y]), hits[0]


def _ink(line):
    return len(line.strip())


def test_every_size_draws_something():
    for size in MARKER_SIZES:
        line, _hb = _draw(size)
        assert _ink(line) >= 1, size


def test_sizes_are_a_real_ladder():
    """Each step must actually be bigger -- an option that renders the same as
    its neighbour is a setting that does nothing."""
    widths = [_ink(_draw(s)[0]) for s in MARKER_SIZES]
    assert widths == [1, 1, 3, 5], widths
    assert _draw("small")[0].strip() != _draw("normal")[0].strip()


def test_marker_span_matches_what_is_drawn():
    for size in MARKER_SIZES:
        line, _hb = _draw(size)
        assert _ink(line) == 2 * marker_span(size) + 1, size


def test_hitbox_covers_the_wings():
    """Clicking a wing has to select the aircraft; it is plainly part of it."""
    for size in MARKER_SIZES:
        _line, (_icao, x0, _y0, x1, _y1) = _draw(size)
        assert x1 - x0 == 2 * marker_span(size), size


def test_label_clears_the_wings():
    for size in MARKER_SIZES:
        line, _hb = _draw(size, label_mode="all")
        assert "SWA22" in line
        wing_end = line.index("SWA22") - 1
        assert line[wing_end] == " ", f"{size}: label collides with the wing"


def test_wings_lie_across_the_heading():
    """A wing drawn along the heading reads as a bar, not an aircraft."""
    for track, wing in ((0.0, "─"), (45.0, "╲"), (90.0, "│"), (135.0, "╱")):
        line, _hb = _draw("large", track=track)
        assert line.strip()[0] == wing, f"track {track}"


def test_unknown_size_falls_back_to_single_cell():
    line, _hb = _draw("bogus")
    assert _ink(line) == 1
    assert marker_span("bogus") == 0


@pytest.mark.parametrize("track", [None, 0.0, 180.0, 359.9])
def test_track_edges_still_draw(track):
    """track_deg is optional on the wire; a plane with no heading still renders."""
    line, _hb = _draw("huge", track=track)
    assert _ink(line) == 5
