from __future__ import annotations

import threading

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm + hail", 99: "thunderstorm + hail",
}


@register_widget
class WeatherWidget(Widget):
    name = "weather"
    title = "Weather"
    default_width = 30
    default_top = 15
    default_left = 68
    default_visible = False

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._data = None
        self._status = "press Refresh"
        self._loading = False

    def build(self, width: int) -> None:
        st = self.ctx.state
        self.add_kv("At", f"{st.lat:+.3f}, {st.lon:+.3f}", width)
        if self._loading:
            self.add_dim("fetching…", width)
        elif self._data:
            d = self._data
            self.add_kv("Temp", f"{d.get('temp','?')}°C", width)
            self.add_kv("Sky", str(d.get("sky", "?")), width)
            self.add_kv("Wind", f"{d.get('wind','?')} km/h", width)
            self.add_kv("Humidity", f"{d.get('humidity','?')}%", width)
        else:
            self.add_dim(self._status, width)
        self.add_blank(width)
        self.add_button("Refresh (Open-Meteo)", width, self._refresh)

    def _refresh(self) -> None:
        if self._loading:
            return
        lat = self.ctx.state.lat
        lon = self.ctx.state.lon
        self._loading = True
        self.ctx.refresh()
        threading.Thread(target=self._fetch, args=(lat, lon), daemon=True).start()

    def _fetch(self, lat: float, lon: float) -> None:
        try:
            import requests
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.4f}&longitude={lon:.4f}"
                "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            )
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            cur = r.json().get("current", {})
            self._data = {
                "temp": cur.get("temperature_2m"),
                "humidity": cur.get("relative_humidity_2m"),
                "wind": cur.get("wind_speed_10m"),
                "sky": _WMO.get(int(cur.get("weather_code", -1)), "?"),
            }
            self._status = "ok"
        except Exception as e:
            self._data = None
            self._status = f"failed: {str(e)[:20]}"
        finally:
            self._loading = False
            self.ctx.refresh()
