
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional, Tuple

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.lakeshark")

RS = 0x1E

_KIND_POSITION  = "CONTACT_POSITION"
_KIND_ALTITUDE  = "CONTACT_ALTITUDE"
_KIND_VELOCITY  = "CONTACT_VELOCITY"
_KIND_IDENT     = "CONTACT_IDENT"
_KIND_NEW       = "CONTACT_NEW"
_KIND_CONFIRMED = "CONTACT_CONFIRMED"
_KIND_LOST      = "CONTACT_LOST"
_KIND_HEARTBEAT = "HEARTBEAT"

_CONTACT_KINDS = {
    _KIND_POSITION, _KIND_ALTITUDE, _KIND_VELOCITY, _KIND_IDENT,
    _KIND_NEW, _KIND_CONFIRMED, _KIND_LOST,
}

@dataclass
class FramedEvent:
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
    if not buf:
        return (), b""

    if bytes([RS]) in buf:
        rs_idx = buf.find(bytes([RS]))
        if rs_idx + 1 < len(buf) and buf[rs_idx + 1:rs_idx + 2] == b"{":
            return _split_rs_framed(buf)

    return _split_brace_balanced(buf)

def _split_rs_framed(buf: bytes) -> Tuple[Iterable[bytes], bytes]:
    parts = buf.split(bytes([RS]))
    if len(parts) < 2:
        return (), buf
    *complete, tail = parts[1:]
    if tail.endswith(b"\n") or tail.endswith(b"\r\n"):
        complete.append(tail)
        leftover = b""
    else:
        leftover = bytes([RS]) + tail
    cleaned = [f.rstrip(b"\r\n") for f in complete if f.strip()]
    return cleaned, leftover

def _split_brace_balanced(buf: bytes) -> Tuple[Iterable[bytes], bytes]:
    frames: list = []
    n = len(buf)

    i = buf.find(b"{")
    if i < 0:
        return (), buf

    while i < n:
        if buf[i:i + 1] != b"{":
            i += 1
            continue

        depth = 0
        in_str = False
        escape = False
        start = i
        end = -1
        spliced = False

        j = i
        while j < n:
            c = buf[j]
            if in_str:
                if escape:
                    escape = False
                elif c == 0x5C:
                    escape = True
                elif c == 0x22:
                    in_str = False
                elif c == 0x7B and j + 4 < n and buf[j + 1:j + 5] == b'"t":':
                    spliced = True
                    break
            else:
                if c == 0x22:
                    in_str = True
                elif c == 0x7B:
                    depth += 1
                elif c == 0x7D:
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            j += 1

        if spliced:
            i = j
            continue

        if end < 0:
            return frames, buf[start:]

        frame = buf[start:end].strip()
        if frame:
            frames.append(frame)

        i = end
        while i < n and buf[i] in (0x20, 0x09, 0x0A, 0x0D, RS, 0x00):
            i += 1
        if i < n and buf[i:i + 1] != b"{":
            next_brace = buf.find(b"{", i)
            if next_brace < 0:
                return frames, buf[i:]
            i = next_brace

    return frames, b""

def parse_frame(frame: bytes) -> Optional[FramedEvent]:
    try:
        obj = json.loads(frame.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    k = obj.get("k")
    if not isinstance(k, str):
        return None
    return FramedEvent(raw=obj, kind=k.upper())

def event_to_aircraft(ev: FramedEvent) -> Optional[Aircraft]:
    if ev.kind not in _CONTACT_KINDS:
        return None
    icao = ev.icao
    if icao is None:
        return None

    raw = ev.raw
    a = Aircraft(icao=icao)

    if ev.kind == _KIND_LOST:
        return a

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
    if pos_flag is False:
        a.lat = None
        a.lon = None

    sq = raw.get("sq") or raw.get("squawk")
    if sq is not None:
        a.squawk = str(sq)

    if "gnd" in raw:
        a.on_ground = bool(raw["gnd"])

    return a

def event_to_status_update(ev: FramedEvent) -> Optional[dict]:
    if ev.kind != _KIND_HEARTBEAT:
        return None
    raw = ev.raw
    out: dict = {"last_heartbeat_at": time.time()}

    direct = (
        ("bps",      "bytes_per_sec",   float),
        ("mps",      "msgs_per_sec",    float),
        ("ac",       "aircraft_active", int),
        ("crc_good", "crc_good",        int),
        ("crc_ok",   "crc_good",        int),
        ("crc_err",  "crc_errors",      int),
    )
    for src, dst, cast in direct:
        v = raw.get(src)
        if v is None:
            continue
        try:
            out[dst] = cast(v)
        except (TypeError, ValueError):
            pass

    mag = raw.get("mag_avg")
    if mag is None:
        mag = raw.get("mag")
    if mag is not None:
        try:
            out["signal_mag"] = float(mag)
        except (TypeError, ValueError):
            pass

    return out

def looks_like_jsonl(buf: bytes) -> bool:
    if not buf:
        return False

    rs = bytes([RS])
    idx = buf.find(rs)
    while idx != -1:
        window = buf[idx + 1: idx + 4]
        if b"{" in window:
            return True
        idx = buf.find(rs, idx + 1)

    if b'"k":' in buf and b'"app":' in buf and buf.find(b"{") >= 0:
        return True

    return False

DEFAULT_TX_PIN = 48

class LakeSharkSerialSource(TrafficSource):

    name = "lakeshark"

    def __init__(
        self,
        registry: AircraftRegistry,
        port: str,
        baudrate: int = 115200,
        tx_pin: int = DEFAULT_TX_PIN,
        prune_interval_s: float = 5.0,
    ) -> None:
        super().__init__(registry)
        self.port = port
        self.baudrate = int(baudrate)
        self.tx_pin = int(tx_pin)
        self.prune_interval_s = float(prune_interval_s)
        self._set_status(name=self.name, detail=f"{port}@{baudrate}")

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
                log.warning("LakeShark serial open failed: %s", e)
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
                continue

            self._set_status(connected=True, detail=f"{self.port}@{self.baudrate}")
            backoff = 0.5
            buf = b""
            connected_at = time.time()
            sniff_done = False

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

                    if (not sniff_done and now - connected_at > 2.0
                            and rate_bytes > 0):
                        st = self.status()
                        if st.messages_total == 0 and not looks_like_jsonl(buf):
                            self._set_status(detail=(
                                f"{self.port}@{self.baudrate} "
                                f"(no JSONL — wrong UART? wire to GPIO {self.tx_pin})"
                            ))
                        sniff_done = True

                    if now - last_rate >= 1.0:
                        elapsed = now - last_rate
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
                log.warning("LakeShark serial read failed: %s", e)
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
        hb = event_to_status_update(ev)
        if hb is not None:
            self._set_status(**hb)
            return

        ac = event_to_aircraft(ev)
        if ac is None:
            return

        if ev.kind == _KIND_LOST:
            self.registry.remove(ac.icao)
            return

        self.registry.upsert(ac)

class LakeSharkReplaySource(TrafficSource):

    name = "lakeshark-replay"

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
                if self._stop_evt.wait(timeout=0.01 / self.speed):
                    return
        self._set_status(detail="replay finished")
        self._stop_evt.wait()
