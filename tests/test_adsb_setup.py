from __future__ import annotations

import json
import socket
import threading

from cartotui.adsb_setup import (
    probe_api,
    probe_config,
    probe_lakeshark,
    probe_replay,
    probe_sbs1,
)
from cartotui.config import Config, _validate
from cartotui.configure import build_parser

SBS1_LINE = ("MSG,3,1,1,A8856D,1,2024/01/01,00:00:00.000,2024/01/01,00:00:00.000,"
             ",5950,,,40.8,-74.5,,,,,,0")


def _serve_once(payload: bytes, ready: threading.Event) -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        ready.set()
        try:
            conn, _ = srv.accept()
            if payload:
                conn.sendall(payload)
            conn.close()
        except OSError:
            pass
        finally:
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def test_sbs1_parses_a_live_feed():
    ready = threading.Event()
    port = _serve_once((SBS1_LINE + "\n").encode() * 6, ready)
    ready.wait(2.0)
    ok, detail = probe_sbs1("127.0.0.1", port, timeout=4.0)
    assert ok is True
    assert "parsed" in detail


def test_sbs1_rejects_a_feed_that_is_not_sbs1():
    ready = threading.Event()
    port = _serve_once(b"hello\nworld\n" * 4, ready)
    ready.wait(2.0)
    ok, detail = probe_sbs1("127.0.0.1", port, timeout=3.0)
    assert ok is False
    assert "none parsed" in detail


def test_sbs1_reports_a_refused_connection():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead = sock.getsockname()[1]
    sock.close()
    ok, detail = probe_sbs1("127.0.0.1", dead, timeout=1.0)
    assert ok is False
    assert "cannot connect" in detail


def test_replay_accepts_jsonl_and_rejects_junk(tmp_path):
    good = tmp_path / "good.jsonl"
    good.write_text(json.dumps({"t": 1.0, "ac": []}) + "\n", encoding="utf-8")
    ok, _ = probe_replay(str(good))
    assert ok is True

    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json at all\n", encoding="utf-8")
    ok, detail = probe_replay(str(bad))
    assert ok is False
    assert "not valid JSONL" in detail

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    ok, detail = probe_replay(str(empty))
    assert ok is False
    assert "empty" in detail

    ok, detail = probe_replay(str(tmp_path / "missing.jsonl"))
    assert ok is False
    assert "no such file" in detail

    ok, detail = probe_replay("")
    assert ok is False


def test_api_rejects_unknown_provider():
    ok, detail = probe_api("not-a-provider", 42.0, -71.0, 50.0)
    assert ok is False
    assert "unknown provider" in detail


def test_api_counts_aircraft(monkeypatch):
    import requests

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ac": [{"hex": "a8856d", "lat": 42.0, "lon": -71.0},
                           {"hex": "bad"},
                           {"hex": "abc123", "lat": 1.0, "lon": 2.0}]}

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp())
    ok, detail = probe_api("airplanes.live", 42.0, -71.0, 50.0)
    assert ok is True
    assert "2 aircraft" in detail


def test_api_empty_sky_is_still_a_working_link(monkeypatch):
    import requests

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ac": []}

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp())
    ok, detail = probe_api("adsb.lol", 0.0, 0.0, 10.0)
    assert ok is True
    assert "no aircraft" in detail


def test_lakeshark_needs_a_port():
    ok, detail = probe_lakeshark("", 115200)
    assert ok is False
    assert "no serial port" in detail


def test_test_config_reports_disabled():
    cfg = Config(_validate({"traffic": {"enabled": False}}), "unused.json")
    ok, detail = probe_config(cfg)
    assert ok is False
    assert "turned off" in detail


def test_test_config_falls_back_to_map_centre_when_following(monkeypatch):
    import cartotui.adsb_setup as mod

    seen = {}

    def fake_api(provider, lat, lon, radius, user_agent="CartoTUI", timeout=10.0):
        seen["lat"] = lat
        seen["lon"] = lon
        return True, "stub"

    monkeypatch.setattr(mod, "probe_api", fake_api)
    cfg = Config(_validate({
        "map": {"center_lat": 51.5, "center_lon": -0.12},
        "traffic": {"enabled": True, "source": "api",
                    "api": {"follow_map": True, "lat": 0.0, "lon": 0.0}},
    }), "unused.json")
    ok, _ = probe_config(cfg)
    assert ok is True
    assert seen["lat"] == 51.5
    assert seen["lon"] == -0.12


def test_lakeshark_tui_survives_validation():
    c = _validate({"traffic": {"enabled": True, "source": "lakeshark_tui",
                               "lakeshark": {"port": "COM3"}}})
    assert c["traffic"]["source"] == "lakeshark_tui"


def test_unknown_source_still_falls_back_to_disabled():
    c = _validate({"traffic": {"source": "lakshark"}})
    assert c["traffic"]["source"] == "disabled"


def _run(argv, cfg_path):
    args = build_parser().parse_args(["--config", str(cfg_path)] + argv)
    return args.func(args)


def test_cmd_adsb_sets_sbs1_without_prompting(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    assert _run(["adsb", "--source", "sbs1", "--host", "10.0.0.9", "--port", "30003"],
                cfg_path) == 0
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert saved["traffic"]["enabled"] is True
    assert saved["traffic"]["source"] == "sbs1"
    assert saved["traffic"]["sbs1"]["host"] == "10.0.0.9"


def test_cmd_adsb_disable(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    _run(["adsb", "--source", "api"], cfg_path)
    assert _run(["adsb", "--disable"], cfg_path) == 0
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert saved["traffic"]["enabled"] is False
    assert saved["traffic"]["source"] == "disabled"


def test_cmd_adsb_api_flags(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    assert _run(["adsb", "--source", "api", "--provider", "adsb.fi",
                 "--radius", "42", "--lat", "51.5", "--lon", "-0.12",
                 "--no-follow-map"], cfg_path) == 0
    api = json.loads(cfg_path.read_text(encoding="utf-8"))["traffic"]["api"]
    assert api["provider"] == "adsb.fi"
    assert api["radius_nm"] == 42.0
    assert api["follow_map"] is False
    assert api["lat"] == 51.5


def test_cmd_adsb_test_flag_returns_nonzero_on_failure(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead = sock.getsockname()[1]
    sock.close()
    rc = _run(["adsb", "--source", "sbs1", "--host", "127.0.0.1",
               "--port", str(dead), "--test"], cfg_path)
    assert rc == 1


def test_configured_source_actually_builds(tmp_path):
    from cartotui.traffic import build_source
    from cartotui.traffic.aircraft import AircraftRegistry

    cfg_path = tmp_path / "cfg.json"
    _run(["adsb", "--source", "sbs1", "--host", "10.0.0.9", "--port", "30003"], cfg_path)
    cfg = Config.load(str(cfg_path))
    src = build_source(cfg.data["traffic"], AircraftRegistry())
    assert src.name == "sbs1"
    assert src.host == "10.0.0.9"


def test_configured_lakeshark_tui_builds_the_tui_source(tmp_path):
    from cartotui.traffic import build_source
    from cartotui.traffic.aircraft import AircraftRegistry

    cfg_path = tmp_path / "cfg.json"
    _run(["adsb", "--source", "lakeshark_tui", "--serial-port", "COM7"], cfg_path)
    cfg = Config.load(str(cfg_path))
    src = build_source(cfg.data["traffic"], AircraftRegistry())
    assert type(src).__name__ == "LakeSharkTUISource"
