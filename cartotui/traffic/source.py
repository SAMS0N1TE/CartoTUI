"""Traffic source abstraction.

A ``TrafficSource`` is a background producer that pushes ``Aircraft`` updates
into an ``AircraftRegistry``. Sources run on their own thread; the UI thread
reads the registry every frame.

Responsibilities of a concrete source:

  * ``start()`` — spin up whatever I/O (serial, socket, etc.) and begin
    pushing into the registry. Must be non-blocking from the caller's
    perspective.
  * ``stop()`` — shut down cleanly within ``shutdown_timeout_s``.
  * ``status()`` — return a current ``LinkStatus`` snapshot for the
    Integration sidebar tab to display.

Sources never raise on transient I/O errors — they log, back off, and retry.
The UI is allowed to assume the source thread either keeps running or is
permanently dead; intermittent flapping is the source's problem to hide.
"""

from __future__ import annotations

import abc
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from cartotui.traffic.aircraft import AircraftRegistry


@dataclass
class LinkStatus:
    """Snapshot of a TrafficSource's current health.

    The Integration tab renders this; it's the user-facing answer to
    "is my receiver actually working?"
    """

    name: str = "none"
    connected: bool = False
    detail: str = ""              # human-readable connection target / error
    last_message_at: Optional[float] = None   # epoch seconds
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
        """Seconds since the last message — None if we've never received one."""
        if self.last_message_at is None:
            return None
        return (now if now is not None else time.time()) - self.last_message_at


class TrafficSource(abc.ABC):
    """Interface for any aircraft data feeder.

    Subclasses provide ``_run()`` — the worker body. ``start()`` and
    ``stop()`` handle the threading boilerplate uniformly.
    """

    name: str = "traffic"

    def __init__(self, registry: AircraftRegistry) -> None:
        self.registry = registry
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._status_lock = threading.Lock()
        self._status = LinkStatus(name=self.name)

    # ----- public lifecycle ------------------------------------------------

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

    # ----- subclass surface ------------------------------------------------

    @abc.abstractmethod
    def _run(self) -> None:
        """Source-specific worker body. Should poll ``self._stop_evt`` to
        exit cleanly. Use ``self._set_status()`` to publish health."""

    def _run_safe(self) -> None:
        try:
            self._run()
        except Exception as e:  # pragma: no cover — defensive only
            self._set_status(connected=False, detail=f"source crashed: {e}")

    # ----- status helpers --------------------------------------------------

    def status(self) -> LinkStatus:
        with self._status_lock:
            # Always attach a live aircraft count — the sidebar should show
            # "what's actually plotted" even between heartbeats.
            self._status.aircraft_active = len(self.registry)
            return LinkStatus(**self._status.__dict__)

    def _set_status(self, **kwargs) -> None:
        with self._status_lock:
            for k, v in kwargs.items():
                setattr(self._status, k, v)

    def _bump(self, **deltas) -> None:
        """Increment numeric counters atomically. Use for ``messages_total``,
        ``parse_errors``, ``crc_good``, ``crc_errors``."""
        with self._status_lock:
            for k, dv in deltas.items():
                setattr(self._status, k, getattr(self._status, k) + dv)


class NullTrafficSource(TrafficSource):
    """Inert source. Used when traffic integration is disabled so the rest
    of the UI can ask for ``status()`` without checking for None."""

    name = "disabled"

    def __init__(self, registry: AircraftRegistry) -> None:
        super().__init__(registry)
        self._set_status(connected=False, detail="traffic disabled in config")

    def _run(self) -> None:
        # Just sit and wait for stop. Heartbeats etc. are no-ops.
        self._stop_evt.wait()
