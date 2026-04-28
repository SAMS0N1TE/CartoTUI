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

  * **Trail history.** Every position update appends a (timestamp, lat,
    lon) sample to ``history``. The deque has a bounded length and an
    age-based prune (``trail_duration_s``) so old samples are dropped.
    The map overlay walks this list to draw fading trail dots behind
    each aircraft. History is *per-aircraft* so it survives a merge —
    we union the two histories sorted by timestamp.

  * **TTL pruning.** Aircraft go out of range or land. We drop entries that
    haven't received an update within ``stale_timeout_s``. Default is 60 s
    which matches dump1090's "live" cutoff.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Deque, Dict, Iterator, List, Optional, Tuple


# Default trail length cap (samples) and duration (seconds). The duration
# is the soft cap — the deque prune drops anything older than this on
# every read. The samples cap is a hard ceiling so a stuck aircraft
# emitting 100 messages/second doesn't grow the trail unbounded.
TRAIL_MAX_SAMPLES = 256
TRAIL_DEFAULT_DURATION_S = 60.0


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

    # Trail history. Stored as a deque of (timestamp, lat, lon) tuples,
    # newest at the right. The registry's ``upsert`` appends a new
    # sample whenever an incoming Aircraft has lat+lon set. Trailing
    # tail is pruned by age via ``prune_history()``.
    history: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=TRAIL_MAX_SAMPLES),
    )

    def merge(self, other: "Aircraft") -> "Aircraft":
        """Return a new Aircraft with non-None fields from ``other`` taking
        precedence. ``first_seen`` is the older of the two; ``last_seen``
        the newer. ``msg_count`` is the sum.

        History is unioned: samples from both inputs are combined and
        sorted by timestamp. The deque cap is applied after merge so
        we never balloon past ``TRAIL_MAX_SAMPLES``.
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
            elif k == "history":
                # Union the two histories. Drop duplicates by timestamp
                # since both inputs may have the same sample if the
                # registry retried an upsert.
                seen = set()
                merged_hist: List[Tuple[float, float, float]] = []
                for sample in list(self.history) + list(other.history):
                    t = sample[0]
                    if t in seen:
                        continue
                    seen.add(t)
                    merged_hist.append(sample)
                merged_hist.sort(key=lambda s: s[0])
                # Cap to TRAIL_MAX_SAMPLES, keeping the newest.
                if len(merged_hist) > TRAIL_MAX_SAMPLES:
                    merged_hist = merged_hist[-TRAIL_MAX_SAMPLES:]
                d[k] = deque(merged_hist, maxlen=TRAIL_MAX_SAMPLES)
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

    def prune_history(self, max_age_s: float = TRAIL_DEFAULT_DURATION_S,
                      now: Optional[float] = None) -> None:
        """Drop trail samples older than ``max_age_s`` from the head of
        the deque. Cheap — O(samples-to-drop) — and called by the
        registry on each upsert so the trail never grows past its
        configured age."""
        if not self.history:
            return
        cutoff = (now if now is not None else time.time()) - max_age_s
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()

    def trail_samples(self, max_age_s: float = TRAIL_DEFAULT_DURATION_S,
                      now: Optional[float] = None) -> List[Tuple[float, float, float]]:
        """Return a copy of the current trail with fresh aging applied.

        Each sample is ``(timestamp, lat, lon)``. The list is ordered
        oldest-first so the overlay can fade them by index.
        """
        cutoff = (now if now is not None else time.time()) - max_age_s
        return [s for s in self.history if s[0] >= cutoff]


class AircraftRegistry:
    """Thread-safe collection of currently-known aircraft.

    Read paths (UI/rasteriser) call ``snapshot()`` which returns a list copy
    so iteration is safe without holding the lock. Writers call ``upsert()``.
    A background prune (``prune_stale()``) runs periodically — typically
    triggered by the source thread after each batch of messages.
    """

    def __init__(
        self,
        stale_timeout_s: float = 60.0,
        trail_duration_s: float = TRAIL_DEFAULT_DURATION_S,
    ) -> None:
        self._lock = threading.RLock()
        self._aircraft: Dict[str, Aircraft] = {}
        self.stale_timeout_s = float(stale_timeout_s)
        self.trail_duration_s = float(trail_duration_s)
        # Generation counter — bumped on every change. UI watches this to
        # avoid re-rendering when nothing's changed.
        self._gen = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._gen

    def upsert(self, ac: Aircraft) -> Aircraft:
        """Merge ``ac`` into the registry by ICAO. Returns the merged result.

        If the incoming Aircraft has a position, append a (timestamp,
        lat, lon) sample to the merged result's history deque. The
        sample timestamp is ``now`` (not the message's ``t`` field)
        because we want trails laid down on receive-time — that's
        what's stable across firmware-vs-host clock drift.
        """
        with self._lock:
            existing = self._aircraft.get(ac.icao)
            merged = ac if existing is None else existing.merge(ac)
            now = time.time()
            merged = replace(
                merged,
                last_seen=now,
                msg_count=(existing.msg_count if existing else 0) + 1,
            )
            # Append a new history sample if this update carries position
            # data. The merge() above already retained any pre-existing
            # samples; we just need to add the new one and prune old ones.
            if merged.has_position():
                # Skip if the previous sample is identical position+within
                # 1 second — common case is a CONTACT_POSITION followed
                # by a CONTACT_ALTITUDE within ms; both have the same
                # lat/lon and shouldn't double-stamp the trail.
                last = merged.history[-1] if merged.history else None
                if (last is None or now - last[0] > 1.0
                        or last[1] != merged.lat or last[2] != merged.lon):
                    merged.history.append((now, merged.lat, merged.lon))
                merged.prune_history(max_age_s=self.trail_duration_s, now=now)
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
