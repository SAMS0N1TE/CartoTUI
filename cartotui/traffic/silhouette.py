
from __future__ import annotations

from typing import List, Optional

_JET = [
    r"    /\    ",
    r" <==||==> ",
    r"   \==/   ",
]
_JUMBO = [
    r"    /\    ",
    r"<===||===>",
    r"  ==||==  ",
    r"   \==/   ",
]
_PROP = [
    r"    ^     ",
    r"  --+--   ",
    r"    |     ",
]
_HELI = [
    r"  \ | /   ",
    r" --(O)--  ",
    r"  / | \   ",
]
_GA = [
    r"    ^     ",
    r"  <-+->   ",
    r"   / \    ",
]
_DEFAULT = _JET

_CATEGORY_ART = {
    "A1": _GA,
    "A2": _PROP,
    "A3": _JET,
    "A4": _JUMBO,
    "A5": _JUMBO,
    "A6": _JET,
    "A7": _HELI,
    "B1": _GA,
    "B4": _GA,
}

_HELI_TYPES = {"R44", "R22", "R66", "EC35", "EC45", "H60", "S76", "A139",
               "AS50", "B06", "B407", "B429", "H500", "EC30", "A109"}

def silhouette(category: Optional[str],
               type_code: Optional[str] = None) -> List[str]:
    cat = (category or "").upper().strip()
    if cat in _CATEGORY_ART:
        return _CATEGORY_ART[cat]
    tc = (type_code or "").upper().strip()
    if tc in _HELI_TYPES:
        return _HELI
    if tc[:2] in ("C1", "C2", "PA", "P2", "DA", "SR"):
        return _GA
    return _DEFAULT
