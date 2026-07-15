
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Deque, Dict, Iterator, List, Optional, Tuple

TRAIL_MAX_SAMPLES = 256
TRAIL_DEFAULT_DURATION_S = 60.0

def project_forward(lat: float, lon: float, track_deg: float,
                    gs_kt: float, seconds: float) -> Tuple[float, float]:
    dist_nm = gs_kt * (seconds / 3600.0)
    dlat = (dist_nm / 60.0) * math.cos(math.radians(track_deg))
    coslat = math.cos(math.radians(lat))
    if abs(coslat) < 1e-6:
        coslat = 1e-6
    dlon = (dist_nm / 60.0) * math.sin(math.radians(track_deg)) / coslat
    return lat + dlat, lon + dlon

@dataclass
class Aircraft:

    icao: str
    callsign: Optional[str] = None
    registration: Optional[str] = None

    type_code: Optional[str] = None
    type_desc: Optional[str] = None
    operator: Optional[str] = None
    category: Optional[str] = None

    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude_ft: Optional[float] = None

    ground_speed_kt: Optional[float] = None
    track_deg: Optional[float] = None
    vertical_rate_fpm: Optional[float] = None
    on_ground: Optional[bool] = None

    squawk: Optional[str] = None
    emergency: Optional[bool] = None
    spi: Optional[bool] = None

    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    msg_count: int = 0

    history: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=TRAIL_MAX_SAMPLES),
    )

    def merge(self, other: "Aircraft") -> "Aircraft":
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
                seen = set()
                merged_hist: List[Tuple[float, float, float]] = []
                for sample in list(self.history) + list(other.history):
                    t = sample[0]
                    if t in seen:
                        continue
                    seen.add(t)
                    merged_hist.append(sample)
                merged_hist.sort(key=lambda s: s[0])
                if len(merged_hist) > TRAIL_MAX_SAMPLES:
                    merged_hist = merged_hist[-TRAIL_MAX_SAMPLES:]
                d[k] = deque(merged_hist, maxlen=TRAIL_MAX_SAMPLES)
            else:
                d[k] = v
        return Aircraft(**d)

    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    def _can_extrapolate(self) -> bool:
        return (self.lat is not None and self.lon is not None
                and self.track_deg is not None
                and self.ground_speed_kt is not None
                and self.ground_speed_kt > 0
                and not self.on_ground)

    def projected_position(self, now: Optional[float] = None,
                           max_dt_s: float = 30.0) -> Optional[Tuple[float, float]]:
        if self.lat is None or self.lon is None:
            return None
        if not self._can_extrapolate():
            return (self.lat, self.lon)
        dt = (now if now is not None else time.time()) - self.last_seen
        if dt <= 0 or dt > max_dt_s:
            return (self.lat, self.lon)
        return project_forward(self.lat, self.lon, self.track_deg,
                               self.ground_speed_kt, dt)

    def position_ahead(self, seconds: float) -> Optional[Tuple[float, float]]:
        if not self._can_extrapolate():
            return None
        return project_forward(self.lat, self.lon, self.track_deg,
                               self.ground_speed_kt, seconds)

    def display_label(self) -> str:
        if self.callsign:
            return self.callsign.strip()
        return self.icao

    def prune_history(self, max_age_s: float = TRAIL_DEFAULT_DURATION_S,
                      now: Optional[float] = None) -> None:
        if not self.history:
            return
        cutoff = (now if now is not None else time.time()) - max_age_s
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()

    def trail_samples(self, max_age_s: float = TRAIL_DEFAULT_DURATION_S,
                      now: Optional[float] = None) -> List[Tuple[float, float, float]]:
        cutoff = (now if now is not None else time.time()) - max_age_s
        return [s for s in self.history if s[0] >= cutoff]

class AircraftRegistry:

    def __init__(
        self,
        stale_timeout_s: float = 60.0,
        trail_duration_s: float = TRAIL_DEFAULT_DURATION_S,
    ) -> None:
        self._lock = threading.RLock()
        self._aircraft: Dict[str, Aircraft] = {}
        self.stale_timeout_s = float(stale_timeout_s)
        self.trail_duration_s = float(trail_duration_s)
        self._gen = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._gen

    def upsert(self, ac: Aircraft) -> Aircraft:
        with self._lock:
            existing = self._aircraft.get(ac.icao)
            merged = ac if existing is None else existing.merge(ac)
            now = time.time()
            merged = replace(
                merged,
                last_seen=now,
                msg_count=(existing.msg_count if existing else 0) + 1,
            )
            if merged.has_position():
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
        cutoff = (now if now is not None else time.time()) - self.stale_timeout_s
        with self._lock:
            stale = [k for k, v in self._aircraft.items() if v.last_seen < cutoff]
            for k in stale:
                del self._aircraft[k]
            if stale:
                self._gen += 1
            return len(stale)

    def snapshot(self) -> List[Aircraft]:
        with self._lock:
            return sorted(self._aircraft.values(), key=lambda a: a.icao)

    def with_position(self) -> List[Aircraft]:
        return [a for a in self.snapshot() if a.has_position()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._aircraft)

    def __iter__(self) -> Iterator[Aircraft]:
        return iter(self.snapshot())

    def clear(self) -> None:
        with self._lock:
            self._aircraft.clear()
            self._gen += 1
