"""LandShark UART → JSONL traffic source.

Reads from a serial port that LandShark's ``output/event_stream`` module
writes to. Frames are ASCII-RS (``0x1E``) prefixed JSON objects, each
followed by an LF or CRLF::

    \x1e{"t":1234,"k":"CONTACT_POSITION","app":"adsb","icao":"A1B2C3", ...}\n

Anything that arrives between an LF and the next ``0x1E`` is human-readable
``ESP_LOG`` text from the same UART and is dropped silently (or routed to
``log.debug`` for inspection). This means we tolerate a serial port that's
sharing log output and event output, which is exactly LandShark's setup.

Network transports (UDP, TCP, MQTT) are intentionally not implemented here.
The framing logic in ``parse_frame()`` is transport-agnostic, so a future
``UDPLandSharkSource`` would be ~30 lines on top of this module.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional, Tuple

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import LinkStatus, TrafficSource

log = logging.getLogger("cartotui.traffic.landshark")

# ASCII record separator — LandShark prefixes every JSONL frame with this so
# the host can demux event-stream JSON from ESP_LOG text on the same UART.
RS = 0x1E

# Event kinds we care about. Listed for readability and for keeping the
# dispatch in one place.
_KIND_POSITION  = "CONTACT_POSITION"
_KIND_ALTITUDE  = "CONTACT_ALTITUDE"
_KIND_VELOCITY  = "CONTACT_VELOCITY"
_KIND_IDENT     = "CONTACT_IDENT"
_KIND_NEW       = "CONTACT_NEW"
_KIND_CONFIRMED = "CONTACT_CONFIRMED"
_KIND_LOST      = "CONTACT_LOST"
_KIND_HEARTBEAT = "HEARTBEAT"   # accept anything heartbeat-shaped

_CONTACT_KINDS = {
    _KIND_POSITION, _KIND_ALTITUDE, _KIND_VELOCITY, _KIND_IDENT,
    _KIND_NEW, _KIND_CONFIRMED, _KIND_LOST,
}


# ---------------------------------------------------------------------------
# Pure parsing (no I/O — easy to unit test)
# ---------------------------------------------------------------------------


@dataclass
class FramedEvent:
    """A single decoded JSONL frame from the LandShark stream."""
    raw: dict
    kind: str

    @property
    def icao(self) -> Optional[str]:
        v = self.raw.get("icao")
        return str(v).upper() if v else None

    @property
    def t(self) -> Optional[float]:
        v = self.raw.get("t")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None


def split_frames(buf: bytes) -> Tuple[Iterable[bytes], bytes]:
    """Split a byte buffer into complete JSONL frames + a trailing tail.

    A frame is everything between two ``0x1E`` markers, or between a
    ``0x1E`` and the end of the buffer if it ends on a newline. Returns
    ``(complete_frames, leftover_tail)`` where ``leftover_tail`` is the
    bytes the caller should keep around to prepend to the next read.
    """
    if not buf:
        return (), b""
    parts = buf.split(bytes([RS]))
    # parts[0] is everything *before* the first RS — non-event prelude
    # (ESP_LOG text). We drop it. parts[1:] are frames.
    if len(parts) < 2:
        return (), buf  # no RS seen yet; keep buffering
    # The last segment may be an incomplete frame: only treat it as complete
    # if it ends in a newline.
    *complete, tail = parts[1:]
    if tail.endswith(b"\n") or tail.endswith(b"\r\n"):
        complete.append(tail)
        leftover = b""
    else:
        leftover = bytes([RS]) + tail
    # Strip trailing CR/LF on each complete frame.
    cleaned = [f.rstrip(b"\r\n") for f in complete if f.strip()]
    return cleaned, leftover


def parse_frame(frame: bytes) -> Optional[FramedEvent]:
    """Parse a single JSONL frame body. Returns None on malformed JSON or
    missing ``k`` field rather than raising — the caller treats None as
    "skip and bump parse_errors"."""
    try:
        obj = json.loads(frame.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    k = obj.get("k")
    if not isinstance(k, str):
        return None
    return FramedEvent(raw=obj, kind=k)


def event_to_aircraft(ev: FramedEvent) -> Optional[Aircraft]:
    """Convert a contact-shaped event to an ``Aircraft`` partial.

    Returns None for events that don't update aircraft state (heartbeats,
    unrecognised kinds). For ``CONTACT_LOST`` returns a sentinel ``Aircraft``
    with ``icao`` set and nothing else — the dispatcher in the source uses
    that as a remove signal rather than an upsert.
    """
    if ev.kind not in _CONTACT_KINDS:
        return None
    icao = ev.icao
    if icao is None:
        return None

    raw = ev.raw
    a = Aircraft(icao=icao)

    if ev.kind == _KIND_LOST:
        return a  # signal-only; dispatcher will call registry.remove()

    # Common fields any contact event may carry. We accept them on whatever
    # event arrives so the merge picks them up incrementally — this is more
    # permissive than the LandShark schema strictly is, but it's robust to
    # schema drift.
    cs = raw.get("cs")
    if isinstance(cs, str) and cs.strip():
        a.callsign = cs.strip()

    for src_key, dst_attr, cast in (
        ("lat", "lat", float),
        ("lon", "lon", float),
        ("alt", "altitude_ft", float),
        ("vel", "ground_speed_kt", float),
        ("hdg", "track_deg", float),
        ("vs",  "vertical_rate_fpm", float),
    ):
        v = raw.get(src_key)
        if v is None:
            continue
        try:
            setattr(a, dst_attr, cast(v))
        except (TypeError, ValueError):
            pass

    pos_flag = raw.get("pos")
    if pos_flag is False and ev.kind == _KIND_POSITION:
        # LandShark says "we have an icao but no resolved position" — leave
        # lat/lon as None.
        a.lat = None
        a.lon = None

    sq = raw.get("sq") or raw.get("squawk")
    if sq is not None:
        a.squawk = str(sq)

    if "gnd" in raw:
        a.on_ground = bool(raw["gnd"])

    return a


def event_to_status_update(ev: FramedEvent) -> Optional[dict]:
    """If ``ev`` is a heartbeat, return the kwargs to push into LinkStatus."""
    if ev.kind != _KIND_HEARTBEAT:
        return None
    raw = ev.raw
    out = {"last_heartbeat_at": time.time()}
    # Accept any of these field names; LandShark schema may evolve.
    for src, dst in (
        ("bps", "bytes_per_sec"),
        ("mps", "msgs_per_sec"),
        ("crc_ok", "crc_good"),
        ("crc_err", "crc_errors"),
        ("mag", "signal_mag"),
        ("ac", "aircraft_active"),
    ):
        v = raw.get(src)
        if v is None:
            continue
        try:
            out[dst] = float(v) if dst in ("bytes_per_sec", "msgs_per_sec",
                                           "signal_mag") else int(v)
        except (TypeError, ValueError):
            pass
    return out


# ---------------------------------------------------------------------------
# Serial source
# ---------------------------------------------------------------------------


class LandSharkSerialSource(TrafficSource):
    """Reads LandShark JSONL events off a serial port.

    Backoff on disconnect: 0.5 s, doubling to 8 s, then steady. Re-opens
    transparently — the UI will see ``connected = False`` while we're
    reconnecting.
    """

    name = "landshark"

    def __init__(
        self,
        registry: AircraftRegistry,
        port: str,
        baudrate: int = 921600,
        prune_interval_s: float = 5.0,
    ) -> None:
        super().__init__(registry)
        self.port = port
        self.baudrate = int(baudrate)
        self.prune_interval_s = float(prune_interval_s)
        self._set_status(name=self.name, detail=f"{port}@{baudrate}")

    def _open_serial(self):
        """Lazy import so pyserial is optional. Returns the open port."""
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "pyserial is not installed. Install it with `pip install pyserial`"
            ) from e
        return serial.Serial(
            self.port,
            baudrate=self.baudrate,
            timeout=0.5,           # short timeout so we can poll _stop_evt
            write_timeout=0.0,
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
                log.warning("LandShark serial open failed: %s", e)
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
                continue

            self._set_status(connected=True, detail=f"{self.port}@{self.baudrate}")
            backoff = 0.5
            buf = b""

            try:
                while not self._stop_evt.is_set():
                    chunk = ser.read(4096)
                    if chunk:
                        buf += chunk
                        rate_bytes += len(chunk)
                        frames, buf = split_frames(buf)
                        for fr in frames:
                            ev = parse_frame(fr)
                            if ev is None:
                                self._bump(parse_errors=1)
                                continue
                            self._dispatch(ev)
                            rate_msgs += 1
                            self._bump(messages_total=1)
                            self._set_status(last_message_at=time.time())

                    now = time.time()
                    if now - last_rate >= 1.0:
                        elapsed = now - last_rate
                        # Smooth a little: simple EMA with alpha 0.5
                        prev = self.status()
                        bps = rate_bytes / elapsed
                        mps = rate_msgs / elapsed
                        self._set_status(
                            bytes_per_sec=0.5 * prev.bytes_per_sec + 0.5 * bps,
                            msgs_per_sec=0.5 * prev.msgs_per_sec + 0.5 * mps,
                        )
                        rate_bytes = 0
                        rate_msgs = 0
                        last_rate = now

                    if now - last_prune >= self.prune_interval_s:
                        self.registry.prune_stale(now)
                        last_prune = now
            except Exception as e:
                log.warning("LandShark serial read failed: %s", e)
                self._set_status(connected=False, detail=f"read error: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
                continue
            finally:
                try:
                    ser.close()
                except Exception:
                    pass

    def _dispatch(self, ev: FramedEvent) -> None:
        # Heartbeat → status only.
        hb = event_to_status_update(ev)
        if hb is not None:
            self._set_status(**hb)
            return

        # Contact event → aircraft delta.
        ac = event_to_aircraft(ev)
        if ac is None:
            return

        if ev.kind == _KIND_LOST:
            self.registry.remove(ac.icao)
            return

        self.registry.upsert(ac)


# ---------------------------------------------------------------------------
# Replay source — for tests + dev without a physical device
# ---------------------------------------------------------------------------


class LandSharkReplaySource(TrafficSource):
    """Replays a captured stream of bytes (e.g. from a `cat /dev/ttyUSB0 > file`
    capture) into the registry. Useful for development on a laptop with no
    hardware attached.

    ``stream`` should yield ``bytes`` chunks; the source treats EOF as
    "stay connected, no new data" rather than disconnecting, so the UI
    behaves the same as with a real device.
    """

    name = "landshark-replay"

    def __init__(
        self,
        registry: AircraftRegistry,
        stream: Callable[[], Iterator[bytes]],
        speed: float = 1.0,
    ) -> None:
        super().__init__(registry)
        self._stream_factory = stream
        self.speed = float(speed)
        self._set_status(name=self.name, detail="replay", connected=True)

    def _run(self) -> None:
        buf = b""
        for chunk in self._stream_factory():
            if self._stop_evt.is_set():
                return
            buf += chunk
            frames, buf = split_frames(buf)
            for fr in frames:
                ev = parse_frame(fr)
                if ev is None:
                    self._bump(parse_errors=1)
                    continue
                self._bump(messages_total=1)
                self._set_status(last_message_at=time.time())
                hb = event_to_status_update(ev)
                if hb is not None:
                    self._set_status(**hb)
                    continue
                ac = event_to_aircraft(ev)
                if ac is None:
                    continue
                if ev.kind == _KIND_LOST:
                    self.registry.remove(ac.icao)
                else:
                    self.registry.upsert(ac)
            if self.speed > 0:
                # Tiny sleep so the replay doesn't peg a core.
                if self._stop_evt.wait(timeout=0.01 / self.speed):
                    return
        # End of stream — keep alive, no new data.
        self._set_status(detail="replay finished")
        self._stop_evt.wait()
