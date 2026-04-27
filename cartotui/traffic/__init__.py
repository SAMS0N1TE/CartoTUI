"""Traffic / aircraft-tracking integration for CartoTUI.

Public API:

  * ``Aircraft``        — single-aircraft state model
  * ``AircraftRegistry`` — thread-safe collection (upsert/prune/snapshot)
  * ``TrafficSource``   — ABC for any data feeder
  * ``LinkStatus``      — health snapshot for the Integration sidebar tab
  * ``NullTrafficSource`` — no-op; used when traffic is disabled
  * ``LandSharkSerialSource`` — reads JSONL from a LandShark UART device
  * ``LandSharkReplaySource`` — replays a captured byte stream (testing)
  * ``SBS1TCPSource``    — reads BaseStation CSV from dump1090's port 30003

Constructing the right source from config is centralised in ``build_source``.
"""

from __future__ import annotations

from typing import Any, Mapping

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.landshark import (
    LandSharkReplaySource,
    LandSharkSerialSource,
    event_to_aircraft,
    event_to_status_update,
    parse_frame,
    split_frames,
)
from cartotui.traffic.sbs1 import SBS1TCPSource, parse_sbs1_line
from cartotui.traffic.source import LinkStatus, NullTrafficSource, TrafficSource

__all__ = [
    "Aircraft", "AircraftRegistry",
    "TrafficSource", "LinkStatus", "NullTrafficSource",
    "LandSharkSerialSource", "LandSharkReplaySource",
    "SBS1TCPSource",
    "parse_frame", "split_frames", "event_to_aircraft", "event_to_status_update",
    "parse_sbs1_line",
    "build_source",
]


def build_source(cfg: Mapping[str, Any], registry: AircraftRegistry) -> TrafficSource:
    """Construct a TrafficSource from the ``traffic`` config block.

    Schema::

        {
          "enabled": bool,
          "source":  "landshark" | "sbs1" | "disabled",
          "stale_timeout_s": float,
          "landshark": {
              "port": "/dev/ttyUSB0" | "COM4",
              "baudrate": int,
          },
          "sbs1": {
              "host": "localhost",
              "port": 30003,
          }
        }

    Returns ``NullTrafficSource`` for any disabled / unknown configuration
    so the UI never has to handle a None.
    """
    if not cfg.get("enabled", False):
        return NullTrafficSource(registry)

    kind = str(cfg.get("source", "disabled")).lower()
    registry.stale_timeout_s = float(cfg.get("stale_timeout_s", registry.stale_timeout_s))

    if kind == "landshark":
        ls = cfg.get("landshark", {})
        port = ls.get("port")
        if not port:
            return NullTrafficSource(registry)
        return LandSharkSerialSource(
            registry,
            port=str(port),
            baudrate=int(ls.get("baudrate", 921600)),
        )

    if kind == "sbs1":
        s = cfg.get("sbs1", {})
        return SBS1TCPSource(
            registry,
            host=str(s.get("host", "localhost")),
            port=int(s.get("port", 30003)),
        )

    return NullTrafficSource(registry)
