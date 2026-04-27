"""SBS-1 BaseStation traffic source.

Secondary adapter for users who already run ``dump1090`` (or any compatible
ADS-B feeder) on their network. SBS-1 BaseStation is a CSV-over-TCP format
that's been the de-facto standard for ~20 years; ``dump1090 --net`` exposes
it on port 30003 by default::

    MSG,3,111,11111,4CA853,111111,2024/01/01,12:00:00.000,2024/01/01,...,52.4567,-1.2345,...

The format splits one aircraft's state across many message types:

    MSG,1 — callsign / identification
    MSG,3 — altitude + lat/lon
    MSG,4 — ground speed + track + vertical rate
    MSG,5 — alt only
    MSG,6 — squawk + emergency flags
    MSG,7 — air/ground status
    MSG,8 — air/ground status

We don't try to be exhaustive — fields-as-they-arrive merging on the
``Aircraft`` instance handles partial records.

LandShark is the primary supported source for this project; SBS-1 is here
so a dump1090 user (or someone testing on a laptop) can also feed CartoTUI
without rebuilding firmware.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Optional

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.sbs1")


def parse_sbs1_line(line: str) -> Optional[Aircraft]:
    """Parse one SBS-1 BaseStation CSV line into an Aircraft partial.

    Returns None for non-MSG records or malformed lines. Field positions
    follow the BaseStation spec — see http://woodair.net/sbs/article/barebones42_socket_data.htm
    for the canonical reference.
    """
    if not line or not line.startswith("MSG,"):
        return None
    parts = line.split(",")
    if len(parts) < 22:
        return None

    msg_type = parts[1].strip()
    icao = parts[4].strip().upper()
    if not icao or len(icao) != 6:
        return None

    a = Aircraft(icao=icao)

    def f(idx: int, cast):
        if idx >= len(parts):
            return None
        v = parts[idx].strip()
        if not v:
            return None
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    # Field index reference (1-based in the spec, 0-based here):
    #   10 callsign, 11 altitude, 12 ground_speed, 13 track,
    #   14 lat, 15 lon, 16 vertical_rate, 17 squawk,
    #   18 alert(?), 19 emergency, 20 spi, 21 on_ground
    if msg_type in ("1",):
        cs = f(10, str)
        if cs:
            a.callsign = cs
    if msg_type in ("3", "5", "6", "7", "8"):
        v = f(11, float)
        if v is not None:
            a.altitude_ft = v
    if msg_type in ("3",):
        lat = f(14, float)
        lon = f(15, float)
        if lat is not None:
            a.lat = lat
        if lon is not None:
            a.lon = lon
    if msg_type in ("4",):
        gs = f(12, float)
        tr = f(13, float)
        vr = f(16, float)
        if gs is not None:
            a.ground_speed_kt = gs
        if tr is not None:
            a.track_deg = tr
        if vr is not None:
            a.vertical_rate_fpm = vr
    if msg_type in ("6",):
        sq = f(17, str)
        if sq:
            a.squawk = sq
        emerg = f(19, str)
        if emerg in ("1", "-1"):
            a.emergency = True
        spi = f(20, str)
        if spi in ("1", "-1"):
            a.spi = True
    if msg_type in ("7", "8"):
        gnd = f(21, str)
        if gnd is not None:
            a.on_ground = gnd in ("1", "-1")

    return a


class SBS1TCPSource(TrafficSource):
    """Reads SBS-1 BaseStation CSV from a TCP server (typically dump1090
    on port 30003)."""

    name = "sbs1"

    def __init__(
        self,
        registry: AircraftRegistry,
        host: str = "localhost",
        port: int = 30003,
        prune_interval_s: float = 5.0,
    ) -> None:
        super().__init__(registry)
        self.host = host
        self.port = int(port)
        self.prune_interval_s = float(prune_interval_s)
        self._set_status(name=self.name, detail=f"{host}:{port}")

    def _run(self) -> None:
        backoff = 0.5
        last_prune = time.time()
        last_rate = time.time()
        rate_msgs = 0
        rate_bytes = 0

        while not self._stop_evt.is_set():
            try:
                sock = socket.create_connection((self.host, self.port), timeout=5.0)
            except OSError as e:
                self._set_status(connected=False, detail=f"connect: {e}")
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
                continue

            sock.settimeout(0.5)
            self._set_status(connected=True, detail=f"{self.host}:{self.port}")
            backoff = 0.5
            buf = b""

            try:
                while not self._stop_evt.is_set():
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        chunk = b""
                    if chunk == b"":
                        # Either timeout (no data) or peer closed. Use a brief
                        # ping-style send to detect closure.
                        try:
                            sock.send(b"")
                        except OSError:
                            raise
                    else:
                        buf += chunk
                        rate_bytes += len(chunk)
                        # SBS is line-delimited.
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            text = line.decode("ascii", errors="replace").strip()
                            if not text:
                                continue
                            ac = parse_sbs1_line(text)
                            if ac is None:
                                self._bump(parse_errors=1)
                                continue
                            self.registry.upsert(ac)
                            rate_msgs += 1
                            self._bump(messages_total=1)
                            self._set_status(last_message_at=time.time())

                    now = time.time()
                    if now - last_rate >= 1.0:
                        elapsed = now - last_rate
                        prev = self.status()
                        self._set_status(
                            bytes_per_sec=0.5 * prev.bytes_per_sec + 0.5 * (rate_bytes / elapsed),
                            msgs_per_sec=0.5 * prev.msgs_per_sec + 0.5 * (rate_msgs / elapsed),
                        )
                        rate_bytes = 0
                        rate_msgs = 0
                        last_rate = now

                    if now - last_prune >= self.prune_interval_s:
                        self.registry.prune_stale(now)
                        last_prune = now
            except OSError as e:
                log.warning("SBS-1 connection lost: %s", e)
                self._set_status(connected=False, detail=f"lost: {e}")
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 8.0)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
