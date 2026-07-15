
from __future__ import annotations

from typing import List, Optional, Tuple

RGB = Tuple[int, int, int]

_STOPS: List[Tuple[float, RGB]] = [
    (0.0,     (222, 40, 40)),
    (2000.0,  (255, 120, 40)),
    (4000.0,  (255, 190, 45)),
    (6000.0,  (232, 226, 60)),
    (8000.0,  (150, 220, 65)),
    (10000.0, (70, 200, 95)),
    (18000.0, (60, 195, 200)),
    (28000.0, (70, 135, 235)),
    (38000.0, (150, 95, 225)),
    (45000.0, (210, 120, 235)),
]

GROUND_COLOR: RGB = (150, 150, 158)
UNKNOWN_COLOR: RGB = (170, 170, 170)

LEGEND_BANDS: List[Tuple[str, RGB]] = [
    ("GND", GROUND_COLOR),
    ("<2k", (222, 40, 40)),
    ("4k", (255, 190, 45)),
    ("6k", (232, 226, 60)),
    ("10k", (70, 200, 95)),
    ("18k", (60, 195, 200)),
    ("28k", (70, 135, 235)),
    ("38k+", (150, 95, 225)),
]

def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )

def altitude_color(alt_ft: Optional[float], on_ground: bool = False) -> RGB:
    if on_ground:
        return GROUND_COLOR
    if alt_ft is None:
        return UNKNOWN_COLOR
    if alt_ft <= _STOPS[0][0]:
        return _STOPS[0][1]
    if alt_ft >= _STOPS[-1][0]:
        return _STOPS[-1][1]
    for i in range(1, len(_STOPS)):
        hi_alt, hi_c = _STOPS[i]
        if alt_ft <= hi_alt:
            lo_alt, lo_c = _STOPS[i - 1]
            span = hi_alt - lo_alt
            t = 0.0 if span <= 0 else (alt_ft - lo_alt) / span
            return _lerp(lo_c, hi_c, t)
    return _STOPS[-1][1]
