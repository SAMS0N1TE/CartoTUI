"""Interactive setup and connection testing for the ADS-B traffic link.

Backs ``cartotui.configure adsb`` and the ADS-B step of setup.sh/setup.ps1.
Every source the traffic factory understands gets a live probe here, so the
wizard can tell "saved" apart from "actually receiving aircraft" before the
user ever launches the TUI.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from cartotui.config import Config

TestResult = Tuple[bool, str]

SOURCE_HELP = {
    "api": "No hardware — free public feed over the internet",
    "sbs1": "dump1090 / readsb / PiAware on this machine or the network",
    "lakeshark": "LakeShark receiver on a USB serial port",
    "lakeshark_tui": "LakeShark receiver, ESP_LOG console format",
    "replay": "Play back a recorded JSONL capture",
    "disabled": "Turn ADS-B traffic off",
}

WIZARD_SOURCES = ["api", "sbs1", "lakeshark", "lakeshark_tui", "replay", "disabled"]

SBS1_PROBE_PORTS = (30003,)
SBS1_PROBE_HOSTS = ("localhost", "127.0.0.1")


def _isatty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _say(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return raw or default


def _ask_bool(prompt: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    raw = _ask(f"{prompt} ({d})").strip().lower()
    if not raw:
        return default
    return raw[0] == "y"


def _ask_float(prompt: str, default: float, lo: float, hi: float) -> float:
    while True:
        raw = _ask(prompt, str(default))
        try:
            v = float(raw)
        except ValueError:
            _say(f"  Not a number: {raw!r}")
            continue
        if not (lo <= v <= hi):
            _say(f"  Must be between {lo} and {hi}.")
            continue
        return v


def _ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    return int(_ask_float(prompt, float(default), float(lo), float(hi)))


def _ask_choice(prompt: str, choices: List[str], default: str) -> str:
    _say()
    for i, name in enumerate(choices, 1):
        mark = "*" if name == default else " "
        _say(f" {mark} {i}) {name:<14} {SOURCE_HELP.get(name, '')}")
    _say()
    while True:
        raw = _ask(prompt, default)
        if raw in choices:
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        _say(f"  Pick 1-{len(choices)} or a name.")


def list_serial_ports() -> List[Tuple[str, str]]:
    """Return ``(device, description)`` for every visible serial port."""
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    out = []
    for p in list_ports.comports():
        out.append((p.device, (p.description or "").strip()))
    return sorted(out)


def probe_sbs1(host: str, port: int, timeout: float = 6.0) -> TestResult:
    """Connect to an SBS-1 feed and try to parse what comes back."""
    from cartotui.traffic.sbs1 import parse_sbs1_line

    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
    except OSError as e:
        return False, f"cannot connect to {host}:{port} — {e}"

    lines = 0
    parsed = 0
    buf = b""
    deadline = time.time() + timeout
    try:
        sock.settimeout(1.0)
        while time.time() < deadline and parsed < 5:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as e:
                return False, f"connected to {host}:{port} but the link dropped — {e}"
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode("ascii", errors="replace").strip()
                if not text:
                    continue
                lines += 1
                if parse_sbs1_line(text) is not None:
                    parsed += 1
    finally:
        try:
            sock.close()
        except Exception:
            pass

    if parsed:
        return True, f"connected to {host}:{port}, parsed {parsed} aircraft message(s)"
    if lines:
        return False, (f"connected to {host}:{port} and got {lines} line(s), but none parsed as "
                       f"SBS-1. Is that port really a BaseStation feed?")
    return False, (f"connected to {host}:{port} but no data arrived in {timeout:.0f}s. "
                   f"The feed may be idle, or dump1090 may have no antenna reception.")


def detect_local_feed() -> Optional[Tuple[str, int]]:
    """Look for a local dump1090-style feed. Returns ``(host, port)`` or None."""
    for host in SBS1_PROBE_HOSTS:
        for port in SBS1_PROBE_PORTS:
            try:
                s = socket.create_connection((host, port), timeout=0.6)
            except OSError:
                continue
            try:
                s.close()
            except Exception:
                pass
            return host, port
    return None


def probe_api(provider: str, lat: float, lon: float, radius_nm: float,
             user_agent: str = "CartoTUI", timeout: float = 10.0) -> TestResult:
    """Hit an ADS-B aggregator once and count usable aircraft."""
    from cartotui.traffic.adsb_api import MAX_RADIUS_NM, PROVIDERS, parse_aircraft

    spec = PROVIDERS.get(provider)
    if spec is None:
        return False, f"unknown provider {provider!r}; expected one of {', '.join(PROVIDERS)}"

    radius = int(max(1, min(MAX_RADIUS_NM, round(radius_nm))))
    url = spec["url"].format(lat=f"{lat:.5f}", lon=f"{lon:.5f}", radius=radius)

    try:
        import requests
    except Exception as e:
        return False, f"requests is not installed — {e}"

    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return False, f"{provider} request failed — {e}"

    raw = data.get(spec["key"]) or []
    good = sum(1 for r in raw if parse_aircraft(r) is not None)
    if good:
        return True, f"{provider} returned {good} aircraft within {radius}nm of {lat:.3f},{lon:.3f}"
    if raw:
        return False, f"{provider} returned {len(raw)} record(s) but none parsed"
    return True, (f"{provider} answered, but no aircraft are within {radius}nm of "
                  f"{lat:.3f},{lon:.3f} right now. The link works; try a busier area.")


def probe_lakeshark(port: str, baudrate: int, timeout: float = 6.0) -> TestResult:
    """Open the LakeShark serial port and see whether bytes flow."""
    if not port:
        return False, "no serial port configured"
    try:
        import serial
    except Exception as e:
        return False, f"pyserial is not installed — {e}"

    try:
        ser = serial.Serial(port, int(baudrate), timeout=1.0)
    except Exception as e:
        return False, f"cannot open {port} at {baudrate} — {e}"

    got = b""
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and len(got) < 512:
            try:
                chunk = ser.read(256)
            except Exception as e:
                return False, f"read failed on {port} — {e}"
            if chunk:
                got += chunk
    finally:
        try:
            ser.close()
        except Exception:
            pass

    if not got:
        return False, (f"opened {port} at {baudrate} but no bytes arrived in {timeout:.0f}s. "
                       f"Check the baud rate and that the receiver is powered.")

    try:
        from cartotui.traffic.lakeshark import looks_like_jsonl
        kind = "JSONL" if looks_like_jsonl(got.decode("utf-8", errors="replace")) else "console/ESP_LOG"
    except Exception:
        kind = "unknown"
    return True, f"{port} at {baudrate} is sending data ({len(got)} bytes, looks like {kind})"


def probe_replay(path: str) -> TestResult:
    """Check that a recorded capture exists and holds readable JSONL."""
    if not path:
        return False, "no replay path configured"
    if not os.path.exists(path):
        return False, f"no such file: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                json.loads(line)
                size = os.path.getsize(path)
                return True, f"{path} is readable JSONL ({size} bytes)"
    except json.JSONDecodeError as e:
        return False, f"{path} is not valid JSONL — {e}"
    except OSError as e:
        return False, f"cannot read {path} — {e}"
    return False, f"{path} is empty"


def probe_config(cfg: Config) -> TestResult:
    """Probe whatever ADS-B source the config currently names."""
    tr = cfg.data.get("traffic", {})
    source = str(tr.get("source", "disabled"))

    if not tr.get("enabled", False):
        return False, "traffic.enabled is false — ADS-B is turned off"

    if source == "sbs1":
        s1 = tr.get("sbs1", {})
        return probe_sbs1(str(s1.get("host", "localhost")), int(s1.get("port", 30003)))

    if source == "api":
        api = tr.get("api", {})
        lat = float(api.get("lat", 0.0))
        lon = float(api.get("lon", 0.0))
        if api.get("follow_map", True) and lat == 0.0 and lon == 0.0:
            m = cfg.data.get("map", {})
            lat = float(m.get("center_lat", 0.0))
            lon = float(m.get("center_lon", 0.0))
        return probe_api(
            str(api.get("provider", "airplanes.live")), lat, lon,
            float(api.get("radius_nm", 100.0)),
            str(cfg.data.get("network", {}).get("user_agent", "CartoTUI")),
        )

    if source in ("lakeshark", "lakeshark_tui"):
        ls = tr.get("lakeshark", {})
        return probe_lakeshark(str(ls.get("port", "")), int(ls.get("baudrate", 115200)))

    if source == "replay":
        return probe_replay(str(tr.get("replay", {}).get("path", "")))

    return False, f"traffic.source is {source!r} — nothing to test"


def _offer_server_install() -> bool:
    """No local feed — offer to stand one up. True if one is now listening."""
    from cartotui import adsb_server

    facts = adsb_server.host_facts()
    backends = adsb_server.plan_backends(facts)
    if not backends:
        return False

    _say("\n  No ADS-B server is running on this machine.")
    status = adsb_server.server_status()
    if status["installed"]:
        _say(f"  Installed but not serving: {', '.join(status['installed'])}")
    if not status["sdr"]:
        _say("  No SDR dongle detected either — a local server needs one.")
        _say("  (The 'api' source needs no hardware at all.)")

    if not _ask_bool("  Set up a local ADS-B server now?", False):
        return False

    names = [b.key for b in backends]
    for i, b in enumerate(backends, 1):
        _say(f"\n  {i}) {b.title}")
        _say(f"     {b.note}")
    _say("")
    pick = _ask("  Backend (number, or blank to skip)", "")
    if not pick.strip():
        return False
    if pick.isdigit() and 1 <= int(pick) <= len(backends):
        backend = backends[int(pick) - 1]
    elif pick in names:
        backend = backends[names.index(pick)]
    else:
        _say("  Skipped.")
        return False

    _say("")
    _say(adsb_server.describe_plan(backend))
    _say("")

    if not backend.automatable or backend.manual_steps:
        _say("  These steps are manual — run them, then re-run: cartotui-config adsb")
        return False
    if not _ask_bool("  Run these commands now?", False):
        _say("  Skipped. Nothing was changed.")
        return False

    rc = adsb_server.run_plan(backend, echo=_say)
    if rc != 0:
        _say("  Install did not complete.")
        return False
    _say("  Installed.")
    return adsb_server.port_open()


def _wizard_sbs1(tr: Dict[str, Any]) -> Dict[str, Any]:
    cur = tr.get("sbs1", {})
    found = detect_local_feed()
    if not found:
        if _offer_server_install():
            found = detect_local_feed()

    if found:
        _say(f"\n  Found a feed listening on {found[0]}:{found[1]}.")
        default_host, default_port = found
    else:
        default_host = str(cur.get("host") or "localhost")
        default_port = int(cur.get("port") or 30003)
        _say("\n  Enter the host running dump1090/readsb (e.g. a Raspberry Pi).")

    host = _ask("  Host", str(default_host))
    port = _ask_int("  Port", int(default_port), 1, 65535)
    return {"source": "sbs1", "sbs1": {"host": host, "port": port}}


def _wizard_api(tr: Dict[str, Any], cfg: Config) -> Dict[str, Any]:
    from cartotui.traffic.adsb_api import PROVIDERS

    cur = tr.get("api", {})
    names = list(PROVIDERS)
    provider = _ask_choice("  Provider", names, str(cur.get("provider") or names[0]))

    follow = _ask_bool("  Follow the map centre as you pan?", bool(cur.get("follow_map", True)))
    lat = float(cur.get("lat", 0.0))
    lon = float(cur.get("lon", 0.0))
    if not follow:
        m = cfg.data.get("map", {})
        lat = _ask_float("  Fixed latitude", lat or float(m.get("center_lat", 0.0)), -90.0, 90.0)
        lon = _ask_float("  Fixed longitude", lon or float(m.get("center_lon", 0.0)), -180.0, 180.0)

    radius = _ask_float("  Radius (nm, max 250)", float(cur.get("radius_nm", 100.0)), 1.0, 250.0)
    interval = _ask_float("  Poll interval (seconds)", float(cur.get("interval_s", 5.0)), 1.0, 3600.0)

    return {
        "source": "api",
        "api": {
            "provider": provider,
            "follow_map": follow,
            "follow_zoom": bool(cur.get("follow_zoom", True)),
            "lat": lat,
            "lon": lon,
            "radius_nm": radius,
            "interval_s": interval,
        },
    }


def _wizard_lakeshark(tr: Dict[str, Any], source: str) -> Dict[str, Any]:
    cur = tr.get("lakeshark", {})
    ports = list_serial_ports()
    if ports:
        _say("\n  Serial ports:")
        for i, (dev, desc) in enumerate(ports, 1):
            _say(f"    {i}) {dev:<12} {desc}")
        default_port = str(cur.get("port") or ports[0][0])
    else:
        _say("\n  No serial ports detected. Plug the receiver in, or type the path by hand.")
        default_port = str(cur.get("port") or "")

    raw = _ask("  Port (name or number)", default_port)
    if raw.isdigit() and ports and 1 <= int(raw) <= len(ports):
        raw = ports[int(raw) - 1][0]
    baud = _ask_int("  Baud rate", int(cur.get("baudrate") or 115200), 1200, 4000000)
    return {"source": source, "lakeshark": {"port": raw, "baudrate": baud}}


def _wizard_replay(tr: Dict[str, Any]) -> Dict[str, Any]:
    cur = tr.get("replay", {})
    path = _ask("  Recording path (.jsonl)", str(cur.get("path") or ""))
    speed = _ask_float("  Playback speed", float(cur.get("speed", 1.0)), 0.1, 60.0)
    loop = _ask_bool("  Loop at end of file?", bool(cur.get("loop", True)))
    return {"source": "replay", "replay": {"path": path, "speed": speed, "loop": loop}}


def run_wizard(cfg: Config, run_test: bool = True) -> int:
    """Walk the user through picking and testing an ADS-B source."""
    if not _isatty():
        _say("ADS-B setup needs an interactive terminal.")
        _say("Run it later with:  cartotui-config adsb")
        return 1

    tr = dict(cfg.data.get("traffic", {}))
    _say()
    _say("ADS-B traffic setup")
    _say("-------------------")
    _say("CartoTUI can overlay live aircraft on the map. Pick where they come from.")
    _say("No receiver hardware? Pick 'api' — it works straight away.")

    choices = list(WIZARD_SOURCES)
    current = str(tr.get("source", "disabled"))
    default = current if current in choices else "api"
    source = _ask_choice("  Source", choices, default)

    if source == "disabled":
        cfg.update({"traffic": {"enabled": False, "source": "disabled"}})
        cfg.save()
        _say(f"\nADS-B disabled. Saved to {cfg.path}")
        return 0

    if source == "sbs1":
        patch = _wizard_sbs1(tr)
    elif source == "api":
        patch = _wizard_api(tr, cfg)
    elif source in ("lakeshark", "lakeshark_tui"):
        patch = _wizard_lakeshark(tr, source)
    else:
        patch = _wizard_replay(tr)

    patch["enabled"] = True
    cfg.update({"traffic": patch})
    cfg.save()
    _say(f"\nSaved to {cfg.path}")

    if not run_test:
        return 0

    if not _ask_bool("\nTest the connection now?", True):
        return 0

    _say("\nTesting...")
    ok, detail = probe_config(cfg)
    if ok:
        _say(f"  OK: {detail}")
        return 0

    _say(f"  Failed: {detail}")
    _say("\nThe setting is saved either way. Re-run with:  cartotui-config adsb")
    return 1


def main(argv=None) -> int:
    from cartotui.configure import build_parser

    args = build_parser().parse_args(["adsb"] + list(argv or []))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
