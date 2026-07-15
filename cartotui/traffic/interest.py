
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

SEV_INFO = 1
SEV_NOTE = 2
SEV_ALERT = 3

EMERGENCY_SQUAWKS = {
    "7500": "HIJACK",
    "7600": "RADIO-FAIL",
    "7700": "EMERGENCY",
}
SPECIAL_SQUAWKS = {
    "7777": "MIL-INTERCEPT",
    "7400": "UAS-LOST-LINK",
}

_MIL_HEX_RANGES: List[Tuple[int, int]] = [
    (0xADF7C8, 0xAFFFFF),
    (0x43C000, 0x43CFFF),
    (0x3B7000, 0x3BFFFF),
    (0x3F4000, 0x3FBFFF),
    (0x33FF00, 0x33FFFF),
    (0x71C000, 0x71FFFF),
    (0x738000, 0x73FFFF),
]

_MIL_CALLSIGN_PREFIXES = (
    "RCH",
    "CNV",
    "RRR",
    "NATO",
    "FORTE",
    "HOMER",
    "GRZLY",
)

@dataclass
class Interest:
    tags: List[str]
    severity: int
    label: str

    @property
    def is_alert(self) -> bool:
        return self.severity >= SEV_ALERT

    def __bool__(self) -> bool:
        return bool(self.tags)

def _hex_int(icao: str) -> Optional[int]:
    try:
        return int(icao, 16)
    except (ValueError, TypeError):
        return None

def _is_military_hex(icao: str) -> bool:
    v = _hex_int(icao)
    if v is None:
        return False
    return any(lo <= v <= hi for lo, hi in _MIL_HEX_RANGES)

def classify(ac) -> Interest:
    tags: List[str] = []
    severity = 0
    badge = ""

    sq = (ac.squawk or "").strip()
    if sq in EMERGENCY_SQUAWKS:
        meaning = EMERGENCY_SQUAWKS[sq]
        tags.append(f"{meaning}:{sq}")
        severity = max(severity, SEV_ALERT)
        badge = meaning
    elif ac.emergency:
        tags.append("EMERGENCY")
        severity = max(severity, SEV_ALERT)
        badge = badge or "EMERGENCY"
    elif sq in SPECIAL_SQUAWKS:
        tags.append(SPECIAL_SQUAWKS[sq])
        severity = max(severity, SEV_NOTE)
        badge = badge or SPECIAL_SQUAWKS[sq]

    cs = (ac.callsign or "").strip().upper()
    is_mil = _is_military_hex(ac.icao) or any(
        cs.startswith(p) for p in _MIL_CALLSIGN_PREFIXES)
    if is_mil:
        tags.append("MIL?")
        severity = max(severity, SEV_NOTE)
        badge = badge or "MIL?"

    if (not ac.on_ground and ac.altitude_ft is not None
            and ac.altitude_ft < 1500
            and ac.ground_speed_kt is not None
            and 0 < ac.ground_speed_kt < 100):
        tags.append("LOW-SLOW")
        severity = max(severity, SEV_INFO)
        badge = badge or "LOW-SLOW"

    return Interest(tags=tags, severity=severity, label=badge)
