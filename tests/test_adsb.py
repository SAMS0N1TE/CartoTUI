
from __future__ import annotations

import os
import time

from cartotui.aircraft_colors import GROUND_COLOR, UNKNOWN_COLOR, altitude_color
from cartotui.traffic.adsb_api import parse_aircraft, radius_for_zoom
from cartotui.traffic.aircraft import Aircraft, AircraftRegistry, project_forward
from cartotui.traffic.interest import classify
from cartotui.traffic.record import (
    AircraftRecorder,
    JSONLReplaySource,
    aircraft_from_dict,
    aircraft_to_dict,
)

def test_parse_aircraft_core_and_enrichment():
    raw = {"hex": "a8856d", "flight": "UAL620  ", "r": "N64809", "t": "B739",
           "desc": "BOEING 737-900", "ownOp": "UNITED AIRLINES INC",
           "alt_baro": 5950, "gs": 269.3, "track": 22.95, "baro_rate": 0,
           "squawk": "4153", "lat": 40.8, "lon": -74.5, "emergency": "none"}
    ac = parse_aircraft(raw)
    assert ac.icao == "A8856D"
    assert ac.callsign == "UAL620"
    assert ac.registration == "N64809"
    assert ac.type_code == "B739"
    assert ac.type_desc == "BOEING 737-900"
    assert ac.operator == "UNITED AIRLINES INC"
    assert ac.altitude_ft == 5950
    assert ac.has_position()
    assert ac.emergency is None or ac.emergency is False

def test_parse_aircraft_ground_and_bad_hex():
    ground = parse_aircraft({"hex": "abc123", "alt_baro": "ground", "lat": 1, "lon": 2})
    assert ground.on_ground is True
    assert ground.altitude_ft == 0.0
    assert parse_aircraft({"hex": "~abc12"}) is None
    assert parse_aircraft({"flight": "NOPE"}) is None

def test_parse_aircraft_emergency_squawk():
    ac = parse_aircraft({"hex": "abc123", "squawk": "7700"})
    assert ac.emergency is True

def test_altitude_color_bands():
    assert altitude_color(None) == UNKNOWN_COLOR
    assert altitude_color(5000, on_ground=True) == GROUND_COLOR
    low = altitude_color(500)
    high = altitude_color(40000)
    assert low != high
    assert low[0] > low[2]
    assert high[2] >= high[0]

def test_project_forward_cardinal():
    la, lo = project_forward(40.0, -74.0, 90.0, 480.0, 60.0)
    assert abs(la - 40.0) < 1e-6
    assert lo > -74.0
    la, lo = project_forward(40.0, -74.0, 0.0, 360.0, 60.0)
    assert la > 40.0
    assert abs(lo - (-74.0)) < 1e-6

def test_projected_position_guards():
    a = Aircraft(icao="ABC123", lat=40.0, lon=-74.0,
                 track_deg=90.0, ground_speed_kt=480.0)
    a.last_seen = time.time() - 5
    p = a.projected_position()
    assert p[1] > -74.0
    a.on_ground = True
    assert a.projected_position() == (40.0, -74.0)
    a.on_ground = False
    a.last_seen = time.time() - 999
    assert a.projected_position() == (40.0, -74.0)

def test_classify_emergency_military_lowslow():
    assert classify(Aircraft(icao="ABC123", squawk="7700")).is_alert
    assert "RADIO-FAIL:7600" in classify(Aircraft(icao="ABC123", squawk="7600")).tags
    assert "MIL?" in classify(Aircraft(icao="AE1234")).tags
    assert "MIL?" in classify(Aircraft(icao="ABC123", callsign="RCH512")).tags
    ls = classify(Aircraft(icao="ABC123", altitude_ft=800,
                           ground_speed_kt=60, on_ground=False))
    assert "LOW-SLOW" in ls.tags
    assert not classify(Aircraft(icao="ABC123", altitude_ft=35000,
                                 ground_speed_kt=450))

def test_radius_for_zoom_monotonic_and_capped():
    assert radius_for_zoom(3, 250) >= radius_for_zoom(12, 250)
    assert radius_for_zoom(3, 40) == 40
    assert radius_for_zoom(16, 250) <= 20

def test_record_replay_roundtrip(tmp_path):
    path = str(tmp_path / "cap.jsonl")
    reg = AircraftRegistry(stale_timeout_s=999)
    reg.upsert(Aircraft(icao="A8856D", callsign="UAL620", type_code="B739",
                        lat=40.8, lon=-74.5, altitude_ft=5950,
                        ground_speed_kt=269, track_deg=23))
    rec = AircraftRecorder(reg, path, interval_s=0.2)
    rec.start()
    time.sleep(0.6)
    reg.upsert(Aircraft(icao="A130CB", callsign="EDV5194", lat=40.9, lon=-74.5,
                        altitude_ft=16200))
    time.sleep(0.5)
    rec.stop()
    assert os.path.getsize(path) > 0

    reg2 = AircraftRegistry(stale_timeout_s=999)
    rep = JSONLReplaySource(reg2, path, speed=10.0, loop=False)
    rep.start()
    time.sleep(1.5)
    rep.stop()
    icaos = {a.icao for a in reg2.snapshot()}
    assert "A8856D" in icaos
    ac = reg2.get("A8856D")
    assert ac.type_code == "B739"

def test_select_visible_filters_and_keeps_forced():
    from cartotui.ui.aircraft_overlay import select_visible
    acs = [Aircraft(icao=f"{i:06X}", lat=40.0 + i * 0.01, lon=-74.0,
                    altitude_ft=1000 * i, ground_speed_kt=300, track_deg=90)
           for i in range(1, 20)]
    acs.append(Aircraft(icao="EMERG1", lat=48.0, lon=-88.0,
                        squawk="7700", altitude_ft=9000))
    acs.append(Aircraft(icao="GRND01", lat=40.05, lon=-74.0,
                        on_ground=True, altitude_ft=0))
    out = select_visible(acs, 40.1, -74.0, max_shown=5,
                         hide_ground=True, keep_icao="000005")
    icaos = {a.icao for a in out}
    assert len(out) == 5
    assert "EMERG1" in icaos
    assert "000005" in icaos
    assert "GRND01" not in icaos

def test_select_visible_altitude_band():
    from cartotui.ui.aircraft_overlay import select_visible
    acs = [Aircraft(icao="LOW001", lat=40.0, lon=-74.0, altitude_ft=500),
           Aircraft(icao="MID001", lat=40.0, lon=-74.0, altitude_ft=20000),
           Aircraft(icao="HIGH01", lat=40.0, lon=-74.0, altitude_ft=40000)]
    out = select_visible(acs, 40.0, -74.0, min_altitude=10000, max_altitude=30000)
    icaos = {a.icao for a in out}
    assert icaos == {"MID001"}

def test_overlay_preserves_map_background():
    import time
    from cartotui.ui.aircraft_overlay import apply_aircraft_overlay
    from cartotui.raster_vector import VectorStyle
    w, h = 40, 12
    rows = [[("fg:#d2d2d2 bg:#4f4f4f", "▀" * w)] for _ in range(h)]
    ac = Aircraft(icao="AAA111", callsign="TEST", lat=40.75, lon=-73.95,
                  altitude_ft=30000, track_deg=90, ground_speed_kt=400)
    ac.last_seen = time.time()
    apply_aircraft_overlay(rows, [ac], center_lat=40.75, center_lon=-73.95, z=11,
                           term_w=w, term_h=h, canvas_px_w=w * 8, canvas_px_h=h * 16,
                           style=VectorStyle(), now=time.time())
    glyphs = set("▲▶▼◀✈")
    for row in rows:
        for style, text in row:
            if any(ch in glyphs for ch in text):
                assert "bg:#" in style

def test_overlay_returns_hitbox_at_marker():
    import time
    from cartotui.ui.aircraft_overlay import apply_aircraft_overlay
    from cartotui.raster_vector import VectorStyle
    w, h = 60, 20
    rows = [[("fg:#d2d2d2 bg:#4f4f4f", "▀" * w)] for _ in range(h)]
    ac = Aircraft(icao="AAA111", callsign="TEST", lat=40.75, lon=-73.95,
                  altitude_ft=30000, track_deg=90, ground_speed_kt=400)
    ac.last_seen = time.time()
    boxes = apply_aircraft_overlay(
        rows, [ac], center_lat=40.75, center_lon=-73.95, z=11,
        term_w=w, term_h=h, canvas_px_w=w * 8, canvas_px_h=h * 16,
        style=VectorStyle(), now=time.time())
    assert boxes, "expected at least one hitbox"
    icao, x0, y0, x1, y1 = boxes[0]
    assert icao == "AAA111"
    assert abs(x0 - w // 2) <= 1 and abs(y0 - h // 2) <= 1
    assert x0 - 1 <= w // 2 <= x1 + 1 and y0 - 1 <= h // 2 <= y1 + 1

def test_marker_glyph_styles():
    from cartotui.ui.aircraft_overlay import _marker_glyph
    assert _marker_glyph(90, "dot") == "•"
    assert _marker_glyph(90, "plane") == "✈"
    assert _marker_glyph(90, "square") == "■"
    assert _marker_glyph(90, "large") == "●"
    assert _marker_glyph(0, "arrow") != _marker_glyph(90, "arrow")

def test_silhouette_by_category():
    from cartotui.traffic.silhouette import silhouette
    heli = silhouette("A7")
    jet = silhouette("A3")
    assert heli != jet
    assert all(isinstance(r, str) for r in heli)
    assert silhouette(None, "R44") == silhouette("A7")
    assert silhouette(None, None)

def test_category_parsed_and_recorded():
    from cartotui.traffic.adsb_api import parse_aircraft
    from cartotui.traffic.record import aircraft_from_dict, aircraft_to_dict
    ac = parse_aircraft({"hex": "abc123", "category": "A7", "lat": 1, "lon": 2})
    assert ac.category == "A7"
    assert aircraft_from_dict(aircraft_to_dict(ac)).category == "A7"

def test_aircraft_dict_roundtrip():
    a = Aircraft(icao="ABC123", callsign="TEST", type_code="B738",
                 operator="ACME", lat=1.0, lon=2.0, altitude_ft=30000)
    d = aircraft_to_dict(a)
    b = aircraft_from_dict(d)
    assert b.icao == "ABC123"
    assert b.operator == "ACME"
    assert b.altitude_ft == 30000
    assert aircraft_from_dict({}) is None


def test_set_interval_honours_the_provider_floor():
    """These are free public endpoints publishing ~1 req/s. Asking for 0.5s must
    settle at the floor and say so, not quietly hammer the API."""
    from cartotui.traffic.adsb_api import PROVIDERS, ADSBApiSource
    from cartotui.traffic.aircraft import AircraftRegistry

    src = ADSBApiSource(AircraftRegistry(), provider="airplanes.live")
    floor = PROVIDERS["airplanes.live"]["min_interval_s"]

    assert src.set_interval(0.5) == floor
    assert src.interval_s == floor
    assert src.set_interval(3.0) == 3.0
    assert src.set_interval(10.0) == 10.0


def test_set_interval_clamps_to_the_ui_range():
    from cartotui.traffic.adsb_api import INTERVAL_MAX_S, ADSBApiSource
    from cartotui.traffic.aircraft import AircraftRegistry

    src = ADSBApiSource(AircraftRegistry())
    assert src.set_interval(9999.0) == INTERVAL_MAX_S
    assert src.set_interval(-5.0) == src.min_interval_s


def test_set_radius_clamps_and_applies():
    from cartotui.traffic.adsb_api import MAX_RADIUS_NM, ADSBApiSource
    from cartotui.traffic.aircraft import AircraftRegistry

    src = ADSBApiSource(AircraftRegistry())
    assert src.set_radius(150) == 150
    assert src.radius_nm == 150
    assert src.set_radius(9999) == MAX_RADIUS_NM
    assert src.set_radius(0) == 1


def test_aircraft_config_section_is_validated():
    """The aircraft block shipped with no coercion, so junk reached the overlay."""
    from cartotui.config import _validate

    c = _validate({
        "aircraft": {"marker_size": "gigantic", "marker_style": "nonsense",
                     "max_shown": -5, "label_mode": "wat"},
        "aircraft_trails": {"duration_s": 99999},
        "traffic": {"api": {"interval_s": 0.5}},
    })

    assert c["aircraft"]["marker_size"] == "normal"
    assert c["aircraft"]["marker_style"] == "arrow"
    assert c["aircraft"]["label_mode"] == "smart"
    assert c["aircraft"]["max_shown"] == 0
    assert c["aircraft_trails"]["duration_s"] == 600.0
    assert c["traffic"]["api"]["interval_s"] == 0.5


def test_valid_aircraft_values_survive_validation():
    from cartotui.config import _validate

    c = _validate({"aircraft": {"marker_size": "huge", "marker_style": "plane",
                                "max_shown": 500}})
    assert c["aircraft"]["marker_size"] == "huge"
    assert c["aircraft"]["marker_style"] == "plane"
    assert c["aircraft"]["max_shown"] == 500
