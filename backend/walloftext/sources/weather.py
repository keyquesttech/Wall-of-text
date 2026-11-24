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
    data: dict | None = None  # normalised for the print kit (print-templates/samples/weather.json)

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
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 6,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m,"
                       "visibility,is_day",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,"
                     "precipitation_sum,snowfall_sum,uv_index_max,sunrise,sunset,wind_gusts_10m_max,"
                     "apparent_temperature_min",
            "hourly": "temperature_2m,precipitation_probability,weather_code,visibility,wind_gusts_10m,"
                      "apparent_temperature,is_day",
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
            if hh in ("09:00", "12:00", "15:00", "18:00", "21:00") and t[:10] == (hr.get("time") or [""])[0][:10]:
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
            data=normalise(d, place, units),
        )


def _at(seq, i, default=None):
    try:
        v = seq[i]
        return default if v is None else v
    except (IndexError, TypeError):
        return default


def normalise(d: dict, place: str, units: str = "C") -> dict:
    """One Open-Meteo forecast response → the shape the print kit reads (PRINT_TEMPLATES 5-6)."""
    cur, day, hr = d.get("current") or {}, d.get("daily") or {}, d.get("hourly") or {}
    dates = day.get("time") or []
    today = dates[0] if dates else (cur.get("time") or "")[:10]
    hm = lambda s: (s or "")[-5:] or None  # noqa: E731
    hourly = []
    for i, t in enumerate(hr.get("time") or []):
        if t[:10] < today:
            continue
        hourly.append({
            "date": t[:10], "time": t[-5:],
            "temperature": _at(hr.get("temperature_2m"), i, 0),
            "precipProb": _at(hr.get("precipitation_probability"), i, 0),
            "weatherCode": _at(hr.get("weather_code"), i, 3),
            "visibility": _at(hr.get("visibility"), i),
            "windGusts": _at(hr.get("wind_gusts_10m"), i),
            "apparentTemperature": _at(hr.get("apparent_temperature"), i),
            "isDay": bool(_at(hr.get("is_day"), i, 1)),
        })
        if len(hourly) >= 48:
            break
    daily = []
    for i in range(1, len(dates)):
        daily.append({
            "date": dates[i],
            "weatherCode": _at(day.get("weather_code"), i, 3),
            "tempMax": _at(day.get("temperature_2m_max"), i, 0),
            "tempMin": _at(day.get("temperature_2m_min"), i, 0),
            "precipProbMax": _at(day.get("precipitation_probability_max"), i, 0),
            "windGustsMax": _at(day.get("wind_gusts_10m_max"), i, 0),
        })
    return {
        "place": place, "units": units,
        "current": {
            "time": cur.get("time"), "temperature": cur.get("temperature_2m", 0),
            "apparentTemperature": cur.get("apparent_temperature", cur.get("temperature_2m", 0)),
            "weatherCode": cur.get("weather_code", 3), "windSpeed": cur.get("wind_speed_10m", 0),
            "windGusts": cur.get("wind_gusts_10m", 0), "visibility": cur.get("visibility"),
            "isDay": bool(cur.get("is_day", 1)),
        },
        "today": {
            "date": today,
            "tempMax": _at(day.get("temperature_2m_max"), 0, 0), "tempMin": _at(day.get("temperature_2m_min"), 0, 0),
            "precipProbMax": _at(day.get("precipitation_probability_max"), 0, 0),
            "precipSum": _at(day.get("precipitation_sum"), 0, 0), "snowfallSum": _at(day.get("snowfall_sum"), 0, 0),
            "uvIndexMax": _at(day.get("uv_index_max"), 0, 0), "weatherCode": _at(day.get("weather_code"), 0, 3),
            "sunrise": hm(_at(day.get("sunrise"), 0)), "sunset": hm(_at(day.get("sunset"), 0)),
            "windGustsMax": _at(day.get("wind_gusts_10m_max"), 0),
            "apparentTempMin": _at(day.get("apparent_temperature_min"), 0),
        },
        "tomorrowSunrise": hm(_at(day.get("sunrise"), 1)),
        "hourly": hourly,
        "daily": daily,
    }
