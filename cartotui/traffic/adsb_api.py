
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

from cartotui.traffic.aircraft import Aircraft, AircraftRegistry
from cartotui.traffic.source import TrafficSource

log = logging.getLogger("cartotui.traffic.adsb_api")

PROVIDERS = {
    "airplanes.live": {
        "url": "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
        "key": "ac",
        "min_interval_s": 1.0,
    },
    "adsb.lol": {
        "url": "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}",
        "key": "ac",
        "min_interval_s": 1.0,
    },
    "adsb.fi": {
        "url": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{radius}",
        "key": "aircraft",
        "min_interval_s": 1.0,
    },
}

DEFAULT_PROVIDER = "airplanes.live"
MAX_RADIUS_NM = 250

INTERVAL_MIN_S = 0.5
INTERVAL_MAX_S = 10.0

GetCenter = Callable[[], Tuple[float, float]]

_ZOOM_RADIUS_NM = {
    0: 250, 1: 250, 2: 250, 3: 250, 4: 250, 5: 250, 6: 220,
    7: 170, 8: 130, 9: 95, 10: 65, 11: 45, 12: 30, 13: 22,
    14: 16, 15: 12, 16: 10,
}

def radius_for_zoom(z: int, cap_nm: float) -> int:
    if z <= 0:
        base = 250
    elif z >= 16:
        base = 10
    else:
        base = _ZOOM_RADIUS_NM.get(int(z), 60)
    return int(max(1, min(MAX_RADIUS_NM, cap_nm, base)))

def _num(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None

def _clean_hex(raw) -> Optional[str]:
    if not raw:
        return None
    h = str(raw).strip().lstrip("~").upper()
    if len(h) != 6:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return h

def parse_aircraft(raw: dict) -> Optional[Aircraft]:
    if not isinstance(raw, dict):
        return None
    icao = _clean_hex(raw.get("hex"))
    if icao is None:
        return None

    a = Aircraft(icao=icao)

    flight = raw.get("flight")
    if flight and str(flight).strip():
        a.callsign = str(flight).strip()

    reg = raw.get("r")
    if reg and str(reg).strip():
        a.registration = str(reg).strip()

    tc = raw.get("t")
    if tc and str(tc).strip():
        a.type_code = str(tc).strip()
    desc = raw.get("desc")
    if desc and str(desc).strip():
        a.type_desc = str(desc).strip()
    op = raw.get("ownOp")
    if op and str(op).strip():
        a.operator = str(op).strip()
    cat = raw.get("category")
    if cat and str(cat).strip():
        a.category = str(cat).strip().upper()

    alt = raw.get("alt_baro")
    if isinstance(alt, str) and alt.strip().lower() == "ground":
        a.on_ground = True
        a.altitude_ft = 0.0
    else:
        av = _num(alt)
        if av is None:
            av = _num(raw.get("alt_geom"))
        if av is not None:
            a.altitude_ft = av

    lat = _num(raw.get("lat"))
    lon = _num(raw.get("lon"))
    if lat is not None and lon is not None:
        a.lat = lat
        a.lon = lon

    gs = _num(raw.get("gs"))
    if gs is not None:
        a.ground_speed_kt = gs

    trk = _num(raw.get("track"))
    if trk is None:
        trk = _num(raw.get("true_heading"))
    if trk is not None:
        a.track_deg = trk

    vr = _num(raw.get("baro_rate"))
    if vr is None:
        vr = _num(raw.get("geom_rate"))
    if vr is not None:
        a.vertical_rate_fpm = vr

    sq = raw.get("squawk")
    if sq and str(sq).strip():
        a.squawk = str(sq).strip()
        if a.squawk in ("7500", "7600", "7700"):
            a.emergency = True

    emerg = raw.get("emergency")
    if emerg and str(emerg).strip().lower() not in ("none", "no", ""):
        a.emergency = True

    if raw.get("spi") in (1, "1", True):
        a.spi = True

    return a

class ADSBApiSource(TrafficSource):

    name = "api"

    def __init__(
        self,
        registry: AircraftRegistry,
        provider: str = DEFAULT_PROVIDER,
        radius_nm: float = 100.0,
        interval_s: float = 5.0,
        follow_map: bool = True,
        follow_zoom: bool = True,
        lat: float = 0.0,
        lon: float = 0.0,
        get_center: Optional[GetCenter] = None,
        get_zoom: Optional[Callable[[], int]] = None,
        user_agent: str = "CartoTUI",
        prune_interval_s: float = 5.0,
    ) -> None:
        super().__init__(registry)
        self.provider = provider if provider in PROVIDERS else DEFAULT_PROVIDER
        spec = PROVIDERS[self.provider]
        self.radius_cap_nm = int(max(1, min(MAX_RADIUS_NM, round(radius_nm))))
        self.radius_nm = self.radius_cap_nm
        self.interval_s = float(max(spec["min_interval_s"], interval_s))
        self.follow_map = bool(follow_map)
        self.follow_zoom = bool(follow_zoom)
        self.static_lat = float(lat)
        self.static_lon = float(lon)
        self._get_center = get_center
        self._get_zoom = get_zoom
        self.user_agent = user_agent or "CartoTUI"
        self.prune_interval_s = float(prune_interval_s)
        self._set_status(
            name=self.name,
            detail=f"{self.provider} r={self.radius_nm}nm",
        )

    @property
    def min_interval_s(self) -> float:
        """The provider's published floor -- the fastest it is polite to poll."""
        return float(PROVIDERS[self.provider]["min_interval_s"])

    def set_interval(self, seconds: float) -> float:
        """Repoint the poll period while running; returns the effective value.

        The run loop reads `interval_s` fresh each cycle, so this takes effect on
        the next one -- no restart, and no reconnect for a source that is only
        polling anyway.
        """
        want = max(INTERVAL_MIN_S, min(INTERVAL_MAX_S, float(seconds)))
        self.interval_s = max(self.min_interval_s, want)
        return self.interval_s

    def set_radius(self, nm: float) -> float:
        """Repoint the fetch radius while running; returns the effective value."""
        self.radius_cap_nm = int(max(1, min(MAX_RADIUS_NM, round(float(nm)))))
        self.radius_nm = self.radius_cap_nm
        return float(self.radius_nm)

    def _center(self) -> Tuple[float, float]:
        if self.follow_map and self._get_center is not None:
            try:
                lat, lon = self._get_center()
                return float(lat), float(lon)
            except Exception:
                pass
        return self.static_lat, self.static_lon

    def _effective_radius(self) -> int:
        if self.follow_zoom and self._get_zoom is not None:
            try:
                return radius_for_zoom(int(self._get_zoom()), self.radius_cap_nm)
            except Exception:
                pass
        return self.radius_cap_nm

    def _url(self, lat: float, lon: float, radius: int) -> str:
        tmpl = PROVIDERS[self.provider]["url"]
        return tmpl.format(lat=f"{lat:.5f}", lon=f"{lon:.5f}", radius=radius)

    def _run(self) -> None:
        import requests

        key = PROVIDERS[self.provider]["key"]
        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent})
        backoff = 1.0
        last_prune = time.time()

        while not self._stop_evt.is_set():
            cycle_start = time.time()
            lat, lon = self._center()
            self.radius_nm = self._effective_radius()
            url = self._url(lat, lon, self.radius_nm)
            try:
                resp = session.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                self._bump(parse_errors=1)
                self._set_status(connected=False, detail=f"{self.provider}: {e}")
                if self._stop_evt.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 30.0)
                continue

            backoff = 1.0
            aircraft = data.get(key) or []
            count = 0
            for raw in aircraft:
                ac = parse_aircraft(raw)
                if ac is None:
                    self._bump(parse_errors=1)
                    continue
                self.registry.upsert(ac)
                count += 1

            now = time.time()
            self._bump(messages_total=count)
            self._set_status(
                connected=True,
                detail=f"{self.provider} r={self.radius_nm}nm @{lat:.2f},{lon:.2f}",
                last_message_at=now,
                msgs_per_sec=count / max(0.001, now - cycle_start),
            )

            if now - last_prune >= self.prune_interval_s:
                self.registry.prune_stale(now)
                last_prune = now

            elapsed = time.time() - cycle_start
            wait = max(0.0, self.interval_s - elapsed)
            if wait and self._stop_evt.wait(timeout=wait):
                return
