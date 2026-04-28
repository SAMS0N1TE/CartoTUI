"""LandShark UART → JSONL traffic source.

Reads JSONL aircraft events from the LandShark ESP32-P4 receiver. The
firmware module ``output/event_stream.c`` (in the LandShark repo)
publishes one JSON object per event on a **dedicated UART** so the
host never has to demultiplex JSON from log text.

  * Wire to the GPIO pin specified by ``STREAM_UART_TX_PIN`` in the
    firmware. The default in shipped firmware is now **GPIO 48** on
    the ESP32-P4-Nano (header pin next to a GND, free of peripheral
    assignments). Older firmware revs used GPIO 17, which isn't
    broken out on the Nano — if your board has it pinned out, set
    ``traffic.landshark.tx_pin`` accordingly so the sidebar reflects
    your wiring.

  * Each frame is prefixed with the ASCII record-separator byte
    ``0x1E`` and terminated with ``\\n``::

        \\x1e{"t":1234,"k":"CONTACT_POSITION","app":"adsb",
              "icao":"A1B2C3","cs":"UAL123","alt":35000,"vel":450,
              "hdg":270,"vs":0,"lat":42.36,"lon":-71.05,
              "pos":true,"shaky":false}\\n

  * Event kinds: ``CONTACT_NEW``, ``CONTACT_CONFIRMED``,
    ``CONTACT_LOST``, ``CONTACT_POSITION``, ``CONTACT_ALTITUDE``,
    ``CONTACT_VELOCITY``, ``CONTACT_IDENT``, plus ``HEARTBEAT``,
    ``APP_SWITCHED``, ``BOOT``, ``SHUTDOWN``, ``DEVICE_ATTACHED``,
    ``DEVICE_DETACHED``, ``TUNER_LOCKED``.

  * Heartbeat schema (from ``event_stream.c::emit_heartbeat``)::

        {"k":"HEARTBEAT","app":"adsb",
         "bps":<uint>, "msgs":<int>, "mps":<int>,
         "crc_good":<int>, "crc_err":<int>, "ac":<int>,
         "mag_avg":<int>, "mag_peak":<int>}

The ``0x1E`` prefix is the resync token: if we join mid-stream we drop
bytes until the next RS. Stray text in front of the first frame is
silently dropped for the same reason.

# Field-name compatibility

Old firmware (pre-2026) used ``crc_ok`` and ``mag``; the current
firmware uses ``crc_good``, ``mag_avg``, ``mag_peak``. ``event_to_status_update``
accepts either set, so a single CartoTUI build talks to both. New
``mag_peak`` is folded into ``LinkStatus.signal_mag`` only when no
``mag_avg`` is present — the average is the more useful number.
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

# ASCII record separator — LandShark prefixes every JSONL frame with
# this so a host can demux event-stream JSON from any log text on the
# same UART, and resync mid-stream after a reboot.
RS = 0x1E

# Event kinds we recognise. Listed in one place so the dispatch is
# easy to keep in sync with the firmware.
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
    """Split a byte buffer into JSON frames + a trailing tail.

    Accepts three wire formats, in order of preference:

      1. **RS-framed** (``\\x1e{...}\\n``) — the firmware's intended
         format from ``event_stream.c``. RS markers + newlines means
         we can resync on either signal and bytes outside frames are
         unambiguously prelude/log.

      2. **Newline-delimited JSON** (``{...}\\n{...}\\n``) — common
         JSONL convention; emitted by some firmware revs that drop
         the RS prefix but keep newlines.

      3. **Concatenated JSON with no separator** (``{...}{...}``) —
         what some firmware builds end up with when neither RS nor
         newline make it through (buffer flushing, log driver
         eating control chars, etc.). We brace-balance: walk the
         buffer counting unescaped braces, emit each frame the
         moment depth returns to 0.

    Whichever format we see, the output is a list of complete JSON
    object bodies (without RS prefix or newline terminator) plus
    leftover bytes the caller should keep for the next read.

    Anything before the first ``{`` or ``\\x1e`` is dropped silently —
    log preludes, partial-frame noise from joining mid-stream, etc.
    """
    if not buf:
        return (), b""

    # Format 1: RS-framed. If we see at least one RS *and* the byte
    # after it is `{`, treat that as authoritative.
    if bytes([RS]) in buf:
        rs_idx = buf.find(bytes([RS]))
        if rs_idx + 1 < len(buf) and buf[rs_idx + 1:rs_idx + 2] == b"{":
            return _split_rs_framed(buf)

    # Format 2 / 3: brace-balanced. This handles both NDJSON and
    # concatenated-no-separator equally well — a closing `}` always
    # ends a frame regardless of what follows.
    return _split_brace_balanced(buf)


def _split_rs_framed(buf: bytes) -> Tuple[Iterable[bytes], bytes]:
    """The original RS-framed parser, kept as a fast path for
    well-behaved firmware."""
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
    """Walk ``buf`` counting unescaped JSON braces, emit each frame
    when depth returns to 0. Tracks string-literal context so braces
    inside strings (``"name":"{not a frame}"``) don't confuse the
    counter.

    Recovers from the firmware bug where a previous emit gets
    truncated mid-string by another thread and the next emit slams
    in without a separator: ``...,"ms{"t":1962...``. The signature
    is "we hit ``{"`` while currently in a string". When that happens
    we discard the corrupt frame in progress and resync from the new
    ``{``. This loses one frame's data per splice — acceptable; the
    alternative of swallowing all bytes after the first corruption
    is much worse.
    """
    frames: list = []
    n = len(buf)

    # Skip junk before the first `{` — that's prelude or log text.
    i = buf.find(b"{")
    if i < 0:
        return (), buf

    while i < n:
        # Each iteration tries to scan one frame starting at `{`.
        if buf[i:i + 1] != b"{":
            # Skip whitespace / RS / leftover newlines between frames.
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
                elif c == 0x5C:  # backslash
                    escape = True
                elif c == 0x22:  # closing quote
                    in_str = False
                elif c == 0x7B and j + 4 < n and buf[j + 1:j + 5] == b'"t":':
                    # Splice recovery: a `{"t":` while we're still
                    # inside a string is the canonical "previous
                    # frame got truncated, new frame started" signal.
                    # The current frame is unrecoverable; jump to the
                    # `{` and treat it as a fresh start.
                    spliced = True
                    break
            else:
                if c == 0x22:  # opening quote
                    in_str = True
                elif c == 0x7B:  # {
                    depth += 1
                elif c == 0x7D:  # }
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            j += 1

        if spliced:
            # Discard corrupt frame; restart at the splice point.
            i = j
            continue

        if end < 0:
            # Frame didn't close — incomplete. Save remainder as
            # leftover for the next read to complete.
            return frames, buf[start:]

        frame = buf[start:end].strip()
        if frame:
            frames.append(frame)

        # Skip any separator bytes (whitespace / RS / newlines)
        # between this frame and the next opening `{`.
        i = end
        while i < n and buf[i] in (0x20, 0x09, 0x0A, 0x0D, RS, 0x00):
            i += 1
        # If the next byte isn't `{`, scan forward to find one. This
        # handles the case where firmware injects log text between
        # event frames — we resync at the next `{`.
        if i < n and buf[i:i + 1] != b"{":
            next_brace = buf.find(b"{", i)
            if next_brace < 0:
                return frames, buf[i:]
            i = next_brace

    return frames, b""


def parse_frame(frame: bytes) -> Optional[FramedEvent]:
    """Parse a single JSONL frame body. Returns None on malformed JSON
    or missing ``k`` field rather than raising.

    Normalises ``k`` to upper-case so dispatch logic (which uses the
    canonical ``CONTACT_NEW`` etc.) works regardless of whether the
    firmware emits ``"k":"contact_new"`` or ``"k":"CONTACT_NEW"``.
    Different firmware revs do different things; both are valid as
    far as we're concerned.
    """
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
    """Convert a contact-shaped event to an ``Aircraft`` partial.

    Returns None for non-aircraft events. For ``CONTACT_LOST`` returns
    a sentinel ``Aircraft`` with ``icao`` set and nothing else — the
    dispatcher treats that as a remove signal rather than an upsert.
    """
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
        # Firmware says "no resolved position for this aircraft yet"
        # — clear any (0, 0) sentinel that came through. Applies to
        # any kind, not just CONTACT_POSITION, because new firmware
        # builds emit pos:false on CONTACT_NEW too.
        a.lat = None
        a.lon = None

    sq = raw.get("sq") or raw.get("squawk")
    if sq is not None:
        a.squawk = str(sq)

    if "gnd" in raw:
        a.on_ground = bool(raw["gnd"])

    return a


def event_to_status_update(ev: FramedEvent) -> Optional[dict]:
    """If ``ev`` is a heartbeat, return kwargs to push into LinkStatus.

    Schema mapping (from ``event_stream.c::emit_heartbeat``)::

        bps      → bytes_per_sec      (link bytes/s)
        msgs     → (not surfaced)     (running total since boot)
        mps      → msgs_per_sec       (decoded frames/s)
        crc_good → crc_good           (good frames since boot)
        crc_err  → crc_errors         (bad frames since boot)
        ac       → aircraft_active
        mag_avg  → signal_mag         (preferred)
        mag_peak → (not surfaced)

    Older firmware revs sent ``crc_ok`` and ``mag``; we accept those
    too so a host can talk to a mixed fleet without drama.
    """
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

    # Signal magnitude: prefer mag_avg over the legacy single mag.
    mag = raw.get("mag_avg")
    if mag is None:
        mag = raw.get("mag")
    if mag is not None:
        try:
            out["signal_mag"] = float(mag)
        except (TypeError, ValueError):
            pass

    return out


# ---------------------------------------------------------------------------
# Format auto-detection
# ---------------------------------------------------------------------------


def looks_like_jsonl(buf: bytes) -> bool:
    """Sniff a buffer to decide whether it carries the JSONL event
    stream or human ESP_LOG text.

    Returns True if either of these patterns appears:

      * **RS-framed JSONL** (``\\x1e{``) — the firmware's ideal
        output from a clean ``event_stream.c`` build.
      * **Bare JSON object** matching the LandShark event schema
        (``{"t":<num>,"k":"...","app":"...",...``). Some firmware
        builds drop the RS prefix; we still want to route them to
        the JSONL parser, not to the ESP_LOG fallback. The
        discriminator is the presence of the ``"k":`` field paired
        with ``"app":`` — that combination doesn't appear in
        normal ESP_LOG output.
    """
    if not buf:
        return False

    # Fast path: RS-framed.
    rs = bytes([RS])
    idx = buf.find(rs)
    while idx != -1:
        window = buf[idx + 1: idx + 4]
        if b"{" in window:
            return True
        idx = buf.find(rs, idx + 1)

    # Slow path: bare JSON. We look for the LandShark event-schema
    # signature — both `"k":` and `"app":` need to appear, otherwise
    # this might just be some unrelated JSON being logged. Both keys
    # appear in every event-stream record per event_stream.c.
    if b'"k":' in buf and b'"app":' in buf and buf.find(b"{") >= 0:
        return True

    return False


# ---------------------------------------------------------------------------
# Serial source
# ---------------------------------------------------------------------------


# Default firmware GPIO pin for the event_stream UART TX.
# - GPIO 17 was the first firmware default but isn't broken out on
#   the ESP32-P4-Nano header.
# - GPIO 48 is the current firmware default for the Nano (pinned next
#   to a GND on the right-side header — easy to wire a 2-conductor
#   cable).
# Users with custom firmware builds set this via config.
DEFAULT_TX_PIN = 48


class LandSharkSerialSource(TrafficSource):
    """Reads LandShark JSONL events off a serial port.

    Reconnects automatically with exponential backoff (0.5 → 8 s).
    The UI sees ``connected = False`` while we're in backoff, then
    flips back to True without any user intervention.

    The host doesn't drive ``tx_pin`` — pyserial talks to the OS
    device file (``/dev/ttyUSB0``, ``COM5``, …), which is wired by
    the user to whatever firmware GPIO is configured. ``tx_pin`` is
    informational only: it gets surfaced in the status detail and
    in the sidebar's "wrong UART?" diagnostic so the user-facing
    message matches what they actually wired.
    """

    name = "landshark"

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
        """Lazy import so pyserial is optional."""
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

                    # After 2 s, if we've seen bytes but no JSONL frame
                    # opener, flag it. Users wiring to the wrong UART
                    # is the single most common reason aircraft don't
                    # appear, and we can detect it from here.
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


# ---------------------------------------------------------------------------
# Replay source — for tests + dev without a physical device
# ---------------------------------------------------------------------------


class LandSharkReplaySource(TrafficSource):
    """Replays a captured stream of bytes (e.g. from
    ``cat /dev/ttyUSB0 > capture.bin``) into the registry. Useful for
    development on a laptop with no hardware attached.

    ``stream`` should yield ``bytes`` chunks; the source treats EOF as
    "stay connected, no new data" rather than disconnecting.
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
                if self._stop_evt.wait(timeout=0.01 / self.speed):
                    return
        self._set_status(detail="replay finished")
        self._stop_evt.wait()
