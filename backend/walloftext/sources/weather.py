"""Weather via Open-Meteo (free, no key) behind a provider interface (BUILD_PLAN 9.1).

The last good forecast is cached for 3 hours so a brief outage still prints
something; beyond that the caller prints "Weather unavailable".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

CACHE_S = 3 * 3600

WMO = {
    0: ("Clear", "☀"), 1: ("Mostly clear", "☀"), 2: ("Partly cloudy", "⛅"), 3: ("Cloudy", "☁"),
    45: ("Fog", "≋"), 48: ("Freezing fog", "≋"),
    51: ("Light drizzle", "☂"), 53: ("Drizzle", "☂"), 55: ("Heavy drizzle", "☂"),
    56: ("Freezing drizzle", "☂"), 57: ("Freezing drizzle", "☂"),
    61: ("Light rain", "☂"), 63: ("Rain", "☂"), 65: ("Heavy rain", "☂"),
    66: ("Freezing rain", "☂"), 67: ("Freezing rain", "☂"),
    71: ("Light snow", "❄"), 73: ("Snow", "❄"), 75: ("Heavy snow", "❄"), 77: ("Snow grains", "❄"),
    80: ("Showers", "☂"), 81: ("Showers", "☂"), 82: ("Heavy showers", "☂"),
    85: ("Snow showers", "❄"), 86: ("Snow showers", "❄"),
    95: ("Thunderstorm", "⚡"), 96: ("Thunderstorm, hail", "⚡"), 99: ("Thunderstorm, hail", "⚡"),
}


@dataclass
class Forecast:
    place: str
    now_temp: float
    now_text: str
    today_max: float
    today_min: float
    rain_chance: int
    today_text: str
    hourly: list[tuple[str, float, int]] = field(default_factory=list)  # (HH:00, temp, rain %)
    units: str = "C"
    fetched_at: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class WeatherProvider(Protocol):
    async def geocode(self, place: str) -> dict | None: ...
    async def forecast(self, lat: float, lon: float, place: str, units: str = "C") -> Forecast: ...


class OpenMeteo:
    GEO = "https://geocoding-api.open-meteo.com/v1/search"
    API = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    def _c(self) -> httpx.AsyncClient:
        return self.client or httpx.AsyncClient(timeout=10, headers={"User-Agent": "walloftext/0.1"})

    async def geocode(self, place: str) -> dict | None:
        c = self._c()
        try:
            r = await c.get(self.GEO, params={"name": place, "count": 1, "language": "en", "format": "json"})
            r.raise_for_status()
            res = (r.json().get("results") or [None])[0]
        finally:
            if c is not self.client:
                await c.aclose()
        if not res:
            return None
        label = ", ".join(x for x in (res.get("name"), res.get("admin1"), res.get("country_code")) if x)
        return {"place": label, "lat": res["latitude"], "lon": res["longitude"]}

    async def forecast(self, lat: float, lon: float, place: str, units: str = "C") -> Forecast:
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "hourly": "temperature_2m,precipitation_probability",
        }
        if units == "F":
            params["temperature_unit"] = "fahrenheit"
        c = self._c()
        try:
            r = await c.get(self.API, params=params)
            r.raise_for_status()
            d = r.json()
        finally:
            if c is not self.client:
                await c.aclose()
        cur, day, hr = d["current"], d["daily"], d.get("hourly", {})
        hourly = []
        for t, temp, rain in zip(hr.get("time", []), hr.get("temperature_2m", []), hr.get("precipitation_probability", [])):
            hh = t[-5:]
            if hh in ("09:00", "12:00", "15:00", "18:00", "21:00"):
                hourly.append((hh, temp, int(rain or 0)))
        return Forecast(
            place=place,
            now_temp=cur["temperature_2m"],
            now_text=WMO.get(cur["weather_code"], ("—", ""))[0],
            today_max=day["temperature_2m_max"][0],
            today_min=day["temperature_2m_min"][0],
            rain_chance=int(day["precipitation_probability_max"][0] or 0),
            today_text=WMO.get(day["weather_code"][0], ("—", ""))[0],
            hourly=hourly,
            units=units,
            fetched_at=time.time(),
        )


def weather_blocks(f: Forecast | None, stale_minutes: int | None = None) -> list[dict]:
    if f is None:
        return [{"type": "text", "text": "Weather unavailable", "size": "S", "align": "center"}]
    u = "°" + ("F" if f.units == "F" else "C")
    blocks = [
        {"type": "banner", "text": f"Weather · {f.place}"},
        {"type": "columns", "left": f"Now {round(f.now_temp)}{u}", "right": f.now_text, "size": "L"},
        {"type": "text", "text": f"{f.today_text}. High {round(f.today_max)}{u}, low {round(f.today_min)}{u}. "
                                 f"Rain {f.rain_chance}%.", "size": "M"},
    ]
    if f.hourly:
        blocks.append({"type": "text", "size": "S", "font": "mono",
                       "text": "  ".join(f"{h[:2]}h {round(t)}{u}" + (f" {r}%" if r >= 20 else "") for h, t, r in f.hourly)})
    if stale_minutes:
        blocks.append({"type": "text", "text": f"(from {stale_minutes} min ago)", "size": "S", "align": "right"})
    return blocks
