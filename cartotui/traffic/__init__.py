"""Traffic source factory.

Builds the right ``TrafficSource`` for the user's config. Auto-detection
of the LakeShark wire format (JSONL vs ESP_LOG TUI) does *not* branch
on baudrate any more — the two share a baud now, so the only reliable
discriminator is what's actually on the wire. Sniffing happens inside
``LakeSharkSerialSource`` itself; the factory just picks the source
class the user asked for.

# Source values

  * ``"lakeshark"``     — JSONL events on a UART (preferred path).
  * ``"lakeshark_tui"`` — ESP_LOG fallback parser (system console UART).
  * ``"sbs1"``          — TCP port 30003 of a dump1090 instance.
  * ``"disabled"``      — explicit no-op. Returns NullTrafficSource.

# Auto-promote rules

If ``traffic.enabled`` is True but ``source`` is ``"disabled"``, and a
``lakeshark.port`` is configured, we promote to ``"lakeshark"``. This
saves one round-trip of "I set port but nothing happens." Strings the
factory doesn't recognise (typos like ``"enabled"`` or ``"true"``)
fall through to NullTrafficSource — they are *not* auto-promoted, so
the user sees the wrong-spelled value and can fix it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.lakeshark import (
    DEFAULT_TX_PIN,
    LakeSharkReplaySource,
    LakeSharkSerialSource,
    event_to_aircraft,
    event_to_status_update,
    looks_like_jsonl,
    parse_frame,
    split_frames,
)
from cartotui.traffic.lakeshark_tui import LakeSharkTUISource
from cartotui.traffic.sbs1 import SBS1TCPSource
from cartotui.traffic.source import LinkStatus, NullTrafficSource, TrafficSource

log = logging.getLogger("cartotui.traffic")

__all__ = [
    "Aircraft",
    "AircraftRegistry",
    "LinkStatus",
    "TrafficSource",
    "NullTrafficSource",
    "LakeSharkSerialSource",
    "LakeSharkReplaySource",
    "LakeSharkTUISource",
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

    if enabled and source == "disabled":
        ls_cfg = cfg.get("lakeshark", {})
        if ls_cfg.get("port"):
            log.info("Auto-promoting source=disabled → lakeshark "
                     "(traffic.enabled=true and port is set).")
            source = "lakeshark"

    if not enabled:
        return NullTrafficSource(registry)

    if source == "lakeshark":
        ls = cfg.get("lakeshark", {})
        return LakeSharkSerialSource(
            registry,
            port=str(ls.get("port", "")),
            baudrate=int(ls.get("baudrate", 115200)),
            tx_pin=int(ls.get("tx_pin", DEFAULT_TX_PIN)),
        )

    if source == "lakeshark_tui":
        ls = cfg.get("lakeshark", {})
        return LakeSharkTUISource(
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

    log.warning(
        "Unrecognised traffic.source = %r; expected one of "
        "'lakeshark', 'lakeshark_tui', 'sbs1', 'disabled'.", source,
    )
    null = NullTrafficSource(registry)
    null._set_status(detail=f"unknown source: {source!r}")
    return null
