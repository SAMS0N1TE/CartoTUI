
from __future__ import annotations

import abc
import threading
import time
from dataclasses import dataclass
from typing import Optional

from cartotui.traffic.aircraft import AircraftRegistry


@dataclass
class LinkStatus:

    name: str = "none"
    connected: bool = False
    detail: str = ""
    last_message_at: Optional[float] = None
    last_heartbeat_at: Optional[float] = None
    messages_total: int = 0
    parse_errors: int = 0
    bytes_per_sec: float = 0.0
    msgs_per_sec: float = 0.0
    crc_good: int = 0
    crc_errors: int = 0
    signal_mag: Optional[float] = None
    aircraft_active: int = 0

    def age_s(self, now: Optional[float] = None) -> Optional[float]:
        if self.last_message_at is None:
            return None
        return (now if now is not None else time.time()) - self.last_message_at

class TrafficSource(abc.ABC):

    name: str = "traffic"

    def __init__(self, registry: AircraftRegistry) -> None:
        self.registry = registry
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._status_lock = threading.Lock()
        self._status = LinkStatus(name=self.name)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run_safe, daemon=True, name=f"traffic-{self.name}",
        )
        self._thread.start()

    def stop(self, timeout_s: float = 3.0) -> None:
        self._stop_evt.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout_s)

    def stopped(self) -> bool:
        return self._stop_evt.is_set()

    @abc.abstractmethod
    def _run(self) -> None:
        pass

    def _run_safe(self) -> None:
        try:
            self._run()
        except Exception as e:
            self._set_status(connected=False, detail=f"source crashed: {e}")

    def status(self) -> LinkStatus:
        with self._status_lock:
            self._status.aircraft_active = len(self.registry)
            return LinkStatus(**self._status.__dict__)

    def _set_status(self, **kwargs) -> None:
        with self._status_lock:
            for k, v in kwargs.items():
                setattr(self._status, k, v)

    def _bump(self, **deltas) -> None:
        with self._status_lock:
            for k, dv in deltas.items():
                setattr(self._status, k, getattr(self._status, k) + dv)

class NullTrafficSource(TrafficSource):

    name = "disabled"

    def __init__(self, registry: AircraftRegistry) -> None:
        super().__init__(registry)
        self._set_status(connected=False, detail="traffic disabled in config")

    def _run(self) -> None:
        self._stop_evt.wait()
