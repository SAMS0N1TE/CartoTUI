"""LandShark ESP_LOG fallback parser.

This is the **fallback** when a user has wired to the system console
UART instead of the dedicated event-stream UART (UART2 / GPIO 17). On
the system console, LandShark's ``log_out.c`` module emits standard
``ESP_LOGI`` / ``ESP_LOGW`` lines for each event — human-readable but
parseable. There is no separate "TUI text mode" in the firmware; this
module's old name reflected an earlier guess about the format.

Wire to GPIO 17 if you can — the JSONL stream there is structured,
exact, and never loses data to log truncation. Use this fallback only
if GPIO 17 isn't accessible (e.g. the board ships without that pin
broken out).

# Pattern source

The patterns below are derived from ``main/log_out.c`` in the
LandShark firmware, specifically these calls in ``on_event()``::

    ESP_LOGI(TAG, "[%s] new      %06lX", src, icao);
    ESP_LOGI(TAG, "[%s] confirm  %06lX %s%s", src, icao, cs, shaky?);
    ESP_LOGW(TAG, "[%s] lost     %06lX %s", src, icao, cs);
    ESP_LOGI(TAG, "[%s] fix      %06lX  %+.4f  %+.4f", src, icao, lat, lon);
    ESP_LOGI(TAG, "[%s] alt      %06lX  %d ft", src, icao, alt);
    ESP_LOGI(TAG, "[%s] vel      %06lX  %d kt  hdg=%d  vs=%d", ...);
    ESP_LOGI(TAG, "[%s] ident    %06lX  %s", src, icao, cs);
    ESP_LOGI(TAG, "[%s] HB iq=%lu B/s msgs=%d (+%d/s) crc=%d/%d "
                  "ac=%d mag=%d/%d", src, bps, msgs, mps, crc_g,
                   crc_e, ac, mag_avg, mag_peak);

ESP_LOG wraps each line with its own preamble — ``I (12345) evt:`` for
INFO, ``W (12345) evt:`` for WARN — so each pattern below is anchored
to the body that follows the tag. The TAG is ``evt`` in the firmware.

A typical line on the wire looks like::

    I (28452) evt: [adsb] fix      A1B2C3   +42.3601  -71.0589

# What this misses

The ESP_LOG path drops three things the JSONL stream gives you:
``CONTACT_NEW`` and ``CONTACT_LOST`` come through as text but don't
include lat/lon, so the registry can't plot them until a separate
``fix`` event lands. ``shaky`` flag (CRC-uncertain frames) shows up
as a trailing ``(shaky)`` literal, currently noted but not surfaced.
Heartbeat ``msgs`` total isn't surfaced in LinkStatus today; the
parser captures it but discards.
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional, Tuple

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.landshark_tui")


# ---------------------------------------------------------------------------
# Line patterns (derived from log_out.c on_event())
# ---------------------------------------------------------------------------
#
# Each pattern is (regex, kind). ``kind`` is one of:
#
#   "fix"        — position update (icao, lat, lon)
#   "alt"        — altitude update
#   "vel"        — velocity / heading / vertical-rate update
#   "ident"      — callsign update from CONTACT_IDENT
#   "confirm"    — CONTACT_CONFIRMED (icao + callsign)
#   "new"        — CONTACT_NEW (icao only)
#   "lost"       — CONTACT_LOST (icao + callsign, source-removed)
#   "heartbeat"  — HB iq=... line
#
# Order matters: more specific patterns first. The shared prefix
# ``\[(?P<src>\w+)\]\s+`` matches the ``[adsb]`` source-app tag so we
# don't accidentally capture words from elsewhere in the line.

_PREFIX = r"\[(?P<src>\w+)\]\s+"

# Position: "[adsb] fix      A1B2C3   +42.3601  -71.0589"
_RE_FIX = re.compile(
    _PREFIX + r"fix\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<lat>[+-]?\d+\.\d+)"
    r"\s+(?P<lon>[+-]?\d+\.\d+)"
)

# Altitude: "[adsb] alt      A1B2C3  35000 ft"
_RE_ALT = re.compile(
    _PREFIX + r"alt\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<alt>-?\d+)\s*ft"
)

# Velocity: "[adsb] vel      A1B2C3  450 kt  hdg=270  vs=0"
_RE_VEL = re.compile(
    _PREFIX + r"vel\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<vel>-?\d+)\s*kt"
    r"\s+hdg=(?P<hdg>-?\d+)"
    r"\s+vs=(?P<vs>-?\d+)"
)

# Ident: "[adsb] ident    A1B2C3  UAL123"
_RE_IDENT = re.compile(
    _PREFIX + r"ident\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<callsign>\S+)"
)

# Confirm: "[adsb] confirm  A1B2C3 UAL123" or "...UAL123 (shaky)"
_RE_CONFIRM = re.compile(
    _PREFIX + r"confirm\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"(?:\s+(?P<callsign>[^\s(]+))?"
    r"(?:\s+\(shaky\))?"
)

# New: "[adsb] new      A1B2C3"
_RE_NEW = re.compile(
    _PREFIX + r"new\s+(?P<icao>[0-9A-Fa-f]{6})"
)

# Lost: "[adsb] lost     A1B2C3 UAL123"
_RE_LOST = re.compile(
    _PREFIX + r"lost\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"(?:\s+(?P<callsign>\S+))?"
)

# Heartbeat: "[adsb] HB iq=12000 B/s msgs=100 (+10/s) crc=1000/5 ac=12 mag=42/120"
_RE_HB = re.compile(
    _PREFIX + r"HB"
    r"\s+iq=(?P<bps>\d+)\s*B/s"
    r"(?:\s+msgs=(?P<msgs>\d+)\s*\(\+(?P<mps>\d+)/s\))?"
    r"(?:\s+crc=(?P<crc_good>\d+)/(?P<crc_err>\d+))?"
    r"(?:\s+ac=(?P<ac>\d+))?"
    r"(?:\s+mag=(?P<mag_avg>-?\d+)/(?P<mag_peak>-?\d+))?"
)


_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (_RE_FIX,     "fix"),
    (_RE_ALT,     "alt"),
    (_RE_VEL,     "vel"),
    (_RE_IDENT,   "ident"),
    (_RE_CONFIRM, "confirm"),
    (_RE_NEW,     "new"),
    (_RE_LOST,    "lost"),
    (_RE_HB,      "heartbeat"),
]


# ---------------------------------------------------------------------------
# ESP_LOG line stripping
# ---------------------------------------------------------------------------
#
# A real line on the wire is::
#
#     I (28452) evt: [adsb] fix      A1B2C3   +42.3601  -71.0589
#
# We strip the ``LEVEL (TIME) TAG: `` preamble before pattern-matching
# so the patterns themselves can be specified against the body only.
# Anchoring this way is more robust than baking the preamble into each
# pattern — TAG can change ("evt", "evt_log", etc.) without forcing a
# rewrite of every contact pattern.

_ESP_LOG_PREAMBLE = re.compile(
    r"^\s*[IWE]\s*\(\d+\)\s+\w+:\s*"
)

# ANSI escape stripper — ESP_LOG can colourise level letters depending
# on board config. Strip first so the preamble regex sees plain text.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _strip_log_preamble(line: str) -> Optional[str]:
    """Return the body of an ESP_LOG line, or None if the line wasn't
    one. Used to reject stray text that doesn't belong to log output."""
    line = _ANSI.sub("", line).rstrip("\r\n")
    m = _ESP_LOG_PREAMBLE.match(line)
    if m is None:
        return None
    return line[m.end():]


# ---------------------------------------------------------------------------
# Line parsing
# ---------------------------------------------------------------------------


def parse_line(line: str) -> Optional[Tuple[str, dict]]:
    """Try to match ``line`` against the known patterns.

    Returns ``(kind, fields)`` where ``kind`` is one of the strings
    listed above (``"fix"``, ``"alt"``, ``"vel"``, …, ``"heartbeat"``),
    or ``None`` if no pattern matched.

    Lines without an ESP_LOG preamble are rejected outright — that
    saves us from accidentally matching aircraft IDs out of a banner
    or boot log.
    """
    body = _strip_log_preamble(line)
    if body is None:
        return None
    for pat, kind in _PATTERNS:
        m = pat.search(body)
        if m is None:
            continue
        groups = {k: v for k, v in m.groupdict().items() if v is not None}
        return (kind, groups)
    return None


def fields_to_aircraft(kind: str, fields: dict) -> Optional[Aircraft]:
    """Coerce raw regex captures to an ``Aircraft`` partial.

    ``kind`` is one of the contact kinds; ``"lost"`` returns a sentinel
    so the dispatcher can call ``registry.remove()``. ``"new"`` and
    ``"confirm"`` carry icao but rarely lat/lon — they're still
    returned so the registry can track that the contact exists, even
    if it hasn't yet been positioned.
    """
    icao = (fields.get("icao") or "").upper()
    if not icao or len(icao) != 6:
        return None
    a = Aircraft(icao=icao)

    cs = fields.get("callsign")
    if cs:
        a.callsign = cs.strip()

    for src, dst in (
        ("lat", "lat"), ("lon", "lon"),
        ("alt", "altitude_ft"), ("vel", "ground_speed_kt"),
        ("hdg", "track_deg"), ("vs", "vertical_rate_fpm"),
    ):
        v = fields.get(src)
        if v is None:
            continue
        try:
            setattr(a, dst, float(v))
        except (TypeError, ValueError):
            pass

    return a


def fields_to_status_update(fields: dict) -> dict:
    """Coerce heartbeat regex captures to LinkStatus update kwargs.

    Maps the human-format heartbeat to the same LinkStatus attribute
    set as the JSONL path uses, so the Integration sidebar tab looks
    identical regardless of which UART the user wired to.
    """
    out: dict = {"last_heartbeat_at": time.time()}
    for src, dst, cast in (
        ("bps",      "bytes_per_sec",   float),
        ("mps",      "msgs_per_sec",    float),
        ("ac",       "aircraft_active", int),
        ("crc_good", "crc_good",        int),
        ("crc_err",  "crc_errors",      int),
        ("mag_avg",  "signal_mag",      float),
    ):
        v = fields.get(src)
        if v is None:
            continue
        try:
            out[dst] = cast(v)
        except (TypeError, ValueError):
            pass
    return out


# ---------------------------------------------------------------------------
# Serial source
# ---------------------------------------------------------------------------


class LandSharkTUISource(TrafficSource):
    """Reads LandShark ESP_LOG lines off a serial port.

    Splits input on ``\\n``, strips ANSI sequences, removes the
    ``LEVEL (TIME) TAG: `` preamble, and tries each contact pattern.
    Anything unmatched is ignored — there's no error count for "did
    not match a pattern" because the system console legitimately
    contains many lines that have nothing to do with aircraft (boot
    banners, Wi-Fi state, RTOS messages, …).

    Default baud is **115200** — the firmware's default console rate.
    """

    name = "landshark-tui"

    def __init__(
        self,
        registry: AircraftRegistry,
        port: str,
        baudrate: int = 115200,
        prune_interval_s: float = 5.0,
    ) -> None:
        super().__init__(registry)
        self.port = port
        self.baudrate = int(baudrate)
        self.prune_interval_s = float(prune_interval_s)
        self._set_status(
            name=self.name,
            detail=f"{port}@{baudrate} (ESP_LOG fallback)",
        )

    def _open_serial(self):
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "pyserial is not installed. Install it with `pip install pyserial`"
            ) from e
        return serial.Serial(
            self.port,
            baudrate=self.baudrate,
            timeout=0.5,
        )

    def _run(self) -> None:
        backoff = 0.5
        last_prune = time.time()
        last_rate = time.time()
        rate_bytes = 0
        rate_msgs = 0

        while not self._stop_evt.is_set():
            try:
                ser = self._open_serial()
            except Exception as e:
                self._set_status(connected=False, detail=f"open failed: {e}")
                log.warning("LandShark TUI open failed: %s", e)
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
                continue

            self._set_status(
                connected=True,
                detail=f"{self.port}@{self.baudrate} (ESP_LOG)",
            )
            backoff = 0.5
            buf = b""

            try:
                while not self._stop_evt.is_set():
                    chunk = ser.read(4096)
                    if chunk:
                        buf += chunk
                        rate_bytes += len(chunk)
                        # Process complete lines.
                        while b"\n" in buf:
                            line_b, buf = buf.split(b"\n", 1)
                            text = line_b.decode("utf-8", errors="replace")
                            res = parse_line(text)
                            if res is None:
                                continue
                            kind, fields = res
                            rate_msgs += 1
                            self._bump(messages_total=1)
                            self._set_status(last_message_at=time.time())
                            if kind == "heartbeat":
                                self._set_status(**fields_to_status_update(fields))
                                continue
                            if kind == "lost":
                                icao = (fields.get("icao") or "").upper()
                                if icao:
                                    self.registry.remove(icao)
                                continue
                            ac = fields_to_aircraft(kind, fields)
                            if ac is not None:
                                self.registry.upsert(ac)

                    now = time.time()
                    if now - last_rate >= 1.0:
                        elapsed = now - last_rate
                        prev = self.status()
                        self._set_status(
                            bytes_per_sec=0.5 * prev.bytes_per_sec
                                + 0.5 * (rate_bytes / elapsed),
                            msgs_per_sec=0.5 * prev.msgs_per_sec
                                + 0.5 * (rate_msgs / elapsed),
                        )
                        rate_bytes = 0
                        rate_msgs = 0
                        last_rate = now

                    if now - last_prune >= self.prune_interval_s:
                        self.registry.prune_stale(now)
                        last_prune = now
            except Exception as e:
                log.warning("LandShark TUI read failed: %s", e)
                self._set_status(connected=False, detail=f"read error: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
            finally:
                try:
                    ser.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Pattern registration helper (for runtime tweaks during dev)
# ---------------------------------------------------------------------------


def add_pattern(regex: str, kind: str) -> None:
    """Register a new pattern at runtime.

    Useful for quick iteration when a firmware build emits a slightly
    different format and you want to try a candidate regex without
    editing this file. The new pattern is inserted at the head of the
    list so it wins over the built-ins.
    """
    _PATTERNS.insert(0, (re.compile(regex), kind))
