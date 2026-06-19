
from __future__ import annotations

import logging
import re
import time
from typing import List, Optional, Tuple

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.lakeshark_tui")

_PREFIX = r"\[(?P<src>\w+)\]\s+"

_RE_FIX = re.compile(
    _PREFIX + r"fix\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<lat>[+-]?\d+\.\d+)"
    r"\s+(?P<lon>[+-]?\d+\.\d+)"
)

_RE_ALT = re.compile(
    _PREFIX + r"alt\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<alt>-?\d+)\s*ft"
)

_RE_VEL = re.compile(
    _PREFIX + r"vel\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<vel>-?\d+)\s*kt"
    r"\s+hdg=(?P<hdg>-?\d+)"
    r"\s+vs=(?P<vs>-?\d+)"
)

_RE_IDENT = re.compile(
    _PREFIX + r"ident\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"\s+(?P<callsign>\S+)"
)

_RE_CONFIRM = re.compile(
    _PREFIX + r"confirm\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"(?:\s+(?P<callsign>[^\s(]+))?"
    r"(?:\s+\(shaky\))?"
)

_RE_NEW = re.compile(
    _PREFIX + r"new\s+(?P<icao>[0-9A-Fa-f]{6})"
)

_RE_LOST = re.compile(
    _PREFIX + r"lost\s+(?P<icao>[0-9A-Fa-f]{6})"
    r"(?:\s+(?P<callsign>\S+))?"
)

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

_ESP_LOG_PREAMBLE = re.compile(
    r"^\s*[IWE]\s*\(\d+\)\s+\w+:\s*"
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

def _strip_log_preamble(line: str) -> Optional[str]:
    line = _ANSI.sub("", line).rstrip("\r\n")
    m = _ESP_LOG_PREAMBLE.match(line)
    if m is None:
        return None
    return line[m.end():]

def parse_line(line: str) -> Optional[Tuple[str, dict]]:
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

class LakeSharkTUISource(TrafficSource):

    name = "lakeshark-tui"

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
            import serial
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
                log.warning("LakeShark TUI open failed: %s", e)
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
                log.warning("LakeShark TUI read failed: %s", e)
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

def add_pattern(regex: str, kind: str) -> None:
    _PATTERNS.insert(0, (re.compile(regex), kind))
