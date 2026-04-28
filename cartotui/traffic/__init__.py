"""Traffic source factory.

Builds the right ``TrafficSource`` for the user's config. Auto-detection
of the LandShark wire format (JSONL vs ESP_LOG TUI) does *not* branch
on baudrate any more — the two share a baud now, so the only reliable
discriminator is what's actually on the wire. Sniffing happens inside
``LandSharkSerialSource`` itself; the factory just picks the source
class the user asked for.

# Source values

  * ``"landshark"``     — JSONL events on a UART (preferred path).
  * ``"landshark_tui"`` — ESP_LOG fallback parser (system console UART).
  * ``"sbs1"``          — TCP port 30003 of a dump1090 instance.
  * ``"disabled"``      — explicit no-op. Returns NullTrafficSource.

# Auto-promote rules

If ``traffic.enabled`` is True but ``source`` is ``"disabled"``, and a
``landshark.port`` is configured, we promote to ``"landshark"``. This
saves one round-trip of "I set port but nothing happens." Strings the
factory doesn't recognise (typos like ``"enabled"`` or ``"true"``)
fall through to NullTrafficSource — they are *not* auto-promoted, so
the user sees the wrong-spelled value and can fix it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import LinkStatus, TrafficSource, NullTrafficSource
from cartotui.traffic.landshark import (
    DEFAULT_TX_PIN,
    LandSharkSerialSource,
    LandSharkReplaySource,
    looks_like_jsonl,
    parse_frame,
    split_frames,
    event_to_aircraft,
    event_to_status_update,
)
from cartotui.traffic.landshark_tui import LandSharkTUISource
from cartotui.traffic.sbs1 import SBS1TCPSource

log = logging.getLogger("cartotui.traffic")

__all__ = [
    "Aircraft",
    "AircraftRegistry",
    "LinkStatus",
    "TrafficSource",
    "NullTrafficSource",
    "LandSharkSerialSource",
    "LandSharkReplaySource",
    "LandSharkTUISource",
    "SBS1TCPSource",
    "build_source",
    "looks_like_jsonl",
    "parse_frame",
    "split_frames",
    "event_to_aircraft",
    "event_to_status_update",
]


def build_source(cfg: dict, registry: AircraftRegistry) -> TrafficSource:
    """Build the configured traffic source.

    ``cfg`` is the ``traffic`` block from the app config. ``registry``
    is the shared ``AircraftRegistry`` the new source will populate.

    Returns a started-but-not-running ``TrafficSource`` — the caller
    is expected to call ``.start()`` after construction.
    """
    if not cfg or not isinstance(cfg, dict):
        return NullTrafficSource(registry)

    enabled = bool(cfg.get("enabled", False))
    source = str(cfg.get("source", "disabled")).lower().strip()

    # Auto-promote: enabled + port set + source is "disabled" → landshark.
    # We don't promote on unknown values so typos stay visible.
    if enabled and source == "disabled":
        ls_cfg = cfg.get("landshark", {})
        if ls_cfg.get("port"):
            log.info("Auto-promoting source=disabled → landshark "
                     "(traffic.enabled=true and port is set).")
            source = "landshark"

    if not enabled:
        return NullTrafficSource(registry)

    if source == "landshark":
        ls = cfg.get("landshark", {})
        return LandSharkSerialSource(
            registry,
            port=str(ls.get("port", "")),
            baudrate=int(ls.get("baudrate", 115200)),
            tx_pin=int(ls.get("tx_pin", DEFAULT_TX_PIN)),
        )

    if source == "landshark_tui":
        ls = cfg.get("landshark", {})
        return LandSharkTUISource(
            registry,
            port=str(ls.get("port", "")),
            baudrate=int(ls.get("baudrate", 115200)),
        )

    if source == "sbs1":
        s1 = cfg.get("sbs1", {})
        return SBS1TCPSource(
            registry,
            host=str(s1.get("host", "localhost")),
            port=int(s1.get("port", 30003)),
        )

    if source == "disabled":
        return NullTrafficSource(registry)

    # Unrecognised value (e.g. "enabled", "true", typos). Surface the
    # bad value in the sidebar detail so the user can spot the typo.
    log.warning(
        "Unrecognised traffic.source = %r; expected one of "
        "'landshark', 'landshark_tui', 'sbs1', 'disabled'.", source,
    )
    null = NullTrafficSource(registry)
    null._set_status(detail=f"unknown source: {source!r}")
    return null
