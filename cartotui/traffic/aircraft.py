"""Aircraft state model + thread-safe registry.

The registry is the single source of truth for "what aircraft do we currently
know about". It's mutated by background `TrafficSource` threads and read by the
UI thread (sidebar + map rasteriser) every frame, so all access is lock-guarded.

Design choices worth flagging:

  * **Keyed by ICAO 24-bit hex address.** Callsigns change (and arrive late
    relative to position reports), tail numbers aren't always broadcast,
    but the ICAO address is the unique-per-airframe identifier on the wire.
    SBS-1 calls this the "HexIdent" field.

  * **Last-known wins per field.** SBS-1 splits an aircraft's state across
    many message types — MSG,1 brings callsign, MSG,3 brings position,
    MSG,4 brings velocity/track, etc. We don't get a single "full" record;
    we accumulate fields onto the same `Aircraft` instance as messages
    arrive. ``Aircraft.merge()`` only overwrites a field if the incoming
    value isn't None, so partial updates don't blank good data.

  * **TTL pruning.** Aircraft go out of range or land. We drop entries that
    haven't received an update within ``stale_timeout_s``. Default is 60 s
    which matches dump1090's "live" cutoff.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from typing import Dict, Iterator, List, Optional


@dataclass
class Aircraft:
    """Snapshot of one aircraft's state.

    All fields except ``icao`` are optional because SBS-1 doesn't deliver
    everything in one message — callsign comes from MSG,1, position from
    MSG,3, velocity/track from MSG,4, squawk from MSG,6, etc. We merge as
    fields arrive.
    """

    icao: str  # 6-char uppercase hex, e.g. "A1B2C3"
    callsign: Optional[str] = None
    registration: Optional[str] = None  # tail number, rarely on the wire

    # Position
    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude_ft: Optional[float] = None

    # Movement
    ground_speed_kt: Optional[float] = None
    track_deg: Optional[float] = None     # true track over ground
    vertical_rate_fpm: Optional[float] = None
    on_ground: Optional[bool] = None

    # ATC bookkeeping
    squawk: Optional[str] = None         # 4-digit octal Mode-A code
    emergency: Optional[bool] = None
    spi: Optional[bool] = None           # ident button pressed

    # Source bookkeeping
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    msg_count: int = 0

    def merge(self, other: "Aircraft") -> "Aircraft":
        """Return a new Aircraft with non-None fields from ``other`` taking
        precedence. ``first_seen`` is the older of the two; ``last_seen``
        the newer. ``msg_count`` is the sum.
        """
        if other.icao != self.icao:
            raise ValueError(f"merge mismatch: {self.icao} vs {other.icao}")
        d = self.__dict__.copy()
        for k, v in other.__dict__.items():
            if v is None:
                continue
            if k == "first_seen":
                d[k] = min(self.first_seen, other.first_seen)
            elif k == "last_seen":
                d[k] = max(self.last_seen, other.last_seen)
            elif k == "msg_count":
                d[k] = self.msg_count + other.msg_count
            else:
                d[k] = v
        return Aircraft(**d)

    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    def display_label(self) -> str:
        """Short label for the map glyph annotation."""
        if self.callsign:
            return self.callsign.strip()
        return self.icao


class AircraftRegistry:
    """Thread-safe collection of currently-known aircraft.

    Read paths (UI/rasteriser) call ``snapshot()`` which returns a list copy
    so iteration is safe without holding the lock. Writers call ``upsert()``.
    A background prune (``prune_stale()``) runs periodically — typically
    triggered by the source thread after each batch of messages.
    """

    def __init__(self, stale_timeout_s: float = 60.0) -> None:
        self._lock = threading.RLock()
        self._aircraft: Dict[str, Aircraft] = {}
        self.stale_timeout_s = float(stale_timeout_s)
        # Generation counter — bumped on every change. UI watches this to
        # avoid re-rendering when nothing's changed.
        self._gen = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._gen

    def upsert(self, ac: Aircraft) -> Aircraft:
        """Merge ``ac`` into the registry by ICAO. Returns the merged result."""
        with self._lock:
            existing = self._aircraft.get(ac.icao)
            merged = ac if existing is None else existing.merge(ac)
            merged = replace(merged, last_seen=time.time(),
                             msg_count=(existing.msg_count if existing else 0) + 1)
            self._aircraft[ac.icao] = merged
            self._gen += 1
            return merged

    def get(self, icao: str) -> Optional[Aircraft]:
        with self._lock:
            return self._aircraft.get(icao.upper())

    def remove(self, icao: str) -> bool:
        with self._lock:
            existed = icao.upper() in self._aircraft
            self._aircraft.pop(icao.upper(), None)
            if existed:
                self._gen += 1
            return existed

    def prune_stale(self, now: Optional[float] = None) -> int:
        """Drop aircraft that haven't been heard from recently. Returns the
        number pruned."""
        cutoff = (now if now is not None else time.time()) - self.stale_timeout_s
        with self._lock:
            stale = [k for k, v in self._aircraft.items() if v.last_seen < cutoff]
            for k in stale:
                del self._aircraft[k]
            if stale:
                self._gen += 1
            return len(stale)

    def snapshot(self) -> List[Aircraft]:
        """Return a list copy of all aircraft, sorted ICAO-ascending."""
        with self._lock:
            return sorted(self._aircraft.values(), key=lambda a: a.icao)

    def with_position(self) -> List[Aircraft]:
        """Snapshot of only those with a known lat/lon — what the map plotter
        actually wants."""
        return [a for a in self.snapshot() if a.has_position()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._aircraft)

    def __iter__(self) -> Iterator[Aircraft]:
        # Snapshot, then iterate. Lock-free for the caller.
        return iter(self.snapshot())

    def clear(self) -> None:
        with self._lock:
            self._aircraft.clear()
            self._gen += 1
