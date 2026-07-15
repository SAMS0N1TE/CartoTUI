
from __future__ import annotations

import json
import logging
import threading
import time
from typing import List, Optional

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.record")

_FIELDS = (
    "icao", "callsign", "registration", "type_code", "type_desc", "operator",
    "category", "lat", "lon", "altitude_ft", "ground_speed_kt", "track_deg",
    "vertical_rate_fpm", "on_ground", "squawk", "emergency", "spi",
)

def aircraft_to_dict(ac: Aircraft) -> dict:
    d = {f: getattr(ac, f) for f in _FIELDS}
    return {k: v for k, v in d.items() if v is not None}

def aircraft_from_dict(d: dict) -> Optional[Aircraft]:
    icao = d.get("icao")
    if not icao:
        return None
    ac = Aircraft(icao=str(icao).upper())
    for f in _FIELDS:
        if f == "icao":
            continue
        if f in d and d[f] is not None:
            setattr(ac, f, d[f])
    return ac

class AircraftRecorder:

    def __init__(self, registry: AircraftRegistry, path: str,
                 interval_s: float = 1.0) -> None:
        self.registry = registry
        self.path = path
        self.interval_s = max(0.2, float(interval_s))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frames_written = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="traffic-recorder")
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout_s)

    def _run(self) -> None:
        try:
            fh = open(self.path, "a", encoding="utf-8")
        except OSError as e:
            log.warning("Cannot open record file %s: %s", self.path, e)
            return
        with fh:
            last_gen = None
            while not self._stop.is_set():
                gen = self.registry.generation
                if gen != last_gen:
                    last_gen = gen
                    frame = {
                        "t": round(time.time(), 3),
                        "ac": [aircraft_to_dict(a)
                               for a in self.registry.with_position()],
                    }
                    try:
                        fh.write(json.dumps(frame, separators=(",", ":")) + "\n")
                        fh.flush()
                        self.frames_written += 1
                    except OSError as e:
                        log.warning("Record write failed: %s", e)
                        return
                if self._stop.wait(timeout=self.interval_s):
                    break

class JSONLReplaySource(TrafficSource):

    name = "replay"

    def __init__(self, registry: AircraftRegistry, path: str,
                 speed: float = 1.0, loop: bool = True) -> None:
        super().__init__(registry)
        self.path = path
        self.speed = max(0.1, float(speed))
        self.loop = bool(loop)
        self._set_status(name=self.name, detail=f"{path} x{self.speed:g}")

    def _load(self) -> List[dict]:
        frames: List[dict] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        frames.append(json.loads(line))
                    except json.JSONDecodeError:
                        self._bump(parse_errors=1)
        except OSError as e:
            self._set_status(connected=False, detail=f"open: {e}")
        return frames

    def _run(self) -> None:
        frames = self._load()
        if not frames:
            self._set_status(connected=False, detail="no frames to replay")
            self._stop_evt.wait()
            return

        self._set_status(connected=True,
                         detail=f"{self.path} x{self.speed:g} ({len(frames)} frames)")
        while not self._stop_evt.is_set():
            prev_t = None
            for frame in frames:
                if self._stop_evt.is_set():
                    return
                ft = frame.get("t")
                if prev_t is not None and ft is not None:
                    wait = max(0.0, (ft - prev_t) / self.speed)
                    if wait and self._stop_evt.wait(timeout=min(wait, 5.0)):
                        return
                prev_t = ft
                count = 0
                for raw in frame.get("ac", []):
                    ac = aircraft_from_dict(raw)
                    if ac is None:
                        continue
                    self.registry.upsert(ac)
                    count += 1
                self._bump(messages_total=count)
                self._set_status(last_message_at=time.time())
            if not self.loop:
                self._set_status(detail=f"{self.path} (replay complete)")
                self._stop_evt.wait()
                return
