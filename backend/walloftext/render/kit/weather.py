"""Weather briefing (PRINT_TEMPLATES 5) and Weather now (6).

Both read the normalised weather data (see print-templates/samples/weather.json,
built by `sources.weather.normalise`).
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from . import tokens as T
from .nodes import Band, Box, Col, Custom, Grid, Meter, Pad, Row, Rule, SectionRule, Text
from .slip import Header, Icon, dt_label

# Thresholds (section 5.1). Settings › weather.thresholds can override them.
THRESHOLDS = {"heat_c": 28, "wind_gust_kmh": 60, "frost_c": 0}

WMO = {
    0: "sunny", 1: "sunny", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "sleet", 57: "sleet", 66: "sleet", 67: "sleet",
    61: "rain", 63: "rain", 80: "rain", 81: "rain", 65: "heavy", 82: "heavy",
    71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
    95: "thunder", 96: "thunder", 99: "thunder",
}

SENTENCE = {
    "sunny": "Clear blue skies all day.", "night": "Clear and still. Cold by dawn.",
    "partly": "Bright spells between clouds.", "cloudy": "Grey all day but staying dry.",
    "fog": "Thick fog until late morning.", "drizzle": "Fine drizzle on and off.",
    "rain": "Rain from {rain_from}, easing tonight.", "heavy": "Downpours. Puddles everywhere.",
    "thunder": "Storms this afternoon. Hail possible.", "snow": "Snow showers, settling on grass.",
    "sleet": "Wintry showers with some hail.", "frost": "Hard frost, then crisp sunshine.",
    "wind": "Strong winds, gusting to {gust}.", "heat": "Hot and sunny. Peak at {peak}.",
}
TIP = {
    "sunny": "SUNSCREEN ON", "night": "A NIGHT FOR STARS", "partly": "LIGHT JACKET", "cloudy": "GREY BUT DRY",
    "fog": "LIGHTS ON, GO SLOW", "drizzle": "HOOD UP", "rain": "TAKE AN UMBRELLA", "heavy": "WATERPROOFS ON",
    "thunder": "STAY IN IF YOU CAN", "snow": "BOOTS ON, GO SLOW", "sleet": "SLIPPY UNDERFOOT",
    "frost": "ICE ON THE ROADS", "wind": "HOLD ON TO YOUR HAT", "heat": "WATER AND SHADE",
}
CELLS = {
    "sunny": ("uv", "sunset"), "night": ("moon", "sunrise"), "partly": ("uv", "sunset"),
    "cloudy": ("feels", "sunset"), "fog": ("visibility", "clears"), "drizzle": ("feels", "sunset"),
    "rain": ("rainfall", "sunset"), "heavy": ("rainfall", "gusts"), "thunder": ("gusts", "rainfall"),
    "snow": ("snowfall", "feels"), "sleet": ("feels", "pavements"), "frost": ("feels_min", "thaw"),
    "wind": ("gusts", "feels"), "heat": ("uv", "sunset"),
}
WET = ("rain", "heavy", "thunder", "drizzle", "snow", "sleet")  # their own sentence already says it


# ------------------------------------------------------------------ data --
def _num(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def r(v) -> int:
    """Round half away from zero (so -0.5 prints as -1, never "-0")."""
    v = _num(v)
    out = int(math.floor(abs(v) + 0.5)) * (1 if v >= 0 else -1)
    return 0 if out == 0 else out


def deg(v) -> str:
    return f"{r(v)}°"


def _hm(s: str | None) -> time | None:
    if not s:
        return None
    try:
        hh, mm = s[-5:].split(":")
        return time(int(hh), int(mm))
    except ValueError:
        return None


def timeline(data: dict, now: datetime) -> list[tuple[datetime, dict]]:
    """Hourly entries with full datetimes. Entries without a "date" follow on from the first
    entry's day (today), rolling over at midnight."""
    out: list[tuple[datetime, dict]] = []
    day = now.date()
    try:
        day = date.fromisoformat(data.get("today", {}).get("date") or "") or day
    except ValueError:
        pass
    prev = None
    for e in data.get("hourly") or []:
        t = _hm(e.get("time"))
        if t is None:
            continue
        if e.get("date"):
            try:
                d = date.fromisoformat(e["date"])
            except ValueError:
                d = day
        else:
            if prev is not None and t < prev:
                day = day + timedelta(days=1)
            d = day
        prev = t
        out.append((datetime.combine(d, t), e))
    return out


def _naive(now: datetime) -> datetime:
    return now.replace(tzinfo=None)


def hours_from(data: dict, now: datetime, count: int | None = None, today_only: bool = False):
    start = _naive(now).replace(minute=0, second=0, microsecond=0)
    hs = [(dt, e) for dt, e in timeline(data, now) if dt >= start]
    if today_only:
        hs = [(dt, e) for dt, e in hs if dt.date() == start.date()]
    return hs[:count] if count else hs


def at_hour(data: dict, when: datetime) -> dict | None:
    tl = timeline(data, when)
    if not tl:
        return None
    return min(tl, key=lambda p: abs((p[0] - when).total_seconds()))[1]


def is_night(data: dict, when: datetime) -> bool:
    today = data.get("today") or {}
    rise, sset = _hm(today.get("sunrise")) or time(7, 0), _hm(today.get("sunset")) or time(18, 0)
    t = when.time()
    return t < rise or t >= sset


def thresholds(data: dict) -> dict:
    th = dict(THRESHOLDS)
    th.update({k: v for k, v in (data.get("thresholds") or {}).items() if k in th})
    if data.get("units") == "F":
        th["heat_c"] = th["heat_c"] * 9 / 5 + 32
        th["frost_c"] = th["frost_c"] * 9 / 5 + 32
    return th


def max_gust(data: dict, now: datetime) -> float:
    today = data.get("today") or {}
    if today.get("windGustsMax") is not None:
        return _num(today["windGustsMax"])
    hs = [_num(e.get("windGusts")) for _, e in hours_from(data, now, today_only=True) if e.get("windGusts") is not None]
    return max(hs + [_num((data.get("current") or {}).get("windGusts"))])


def condition(data: dict, now: datetime) -> str:
    """Section 5.1: the WMO code for the day (the current hour's after 18:00), then overrides."""
    today, cur = data.get("today") or {}, data.get("current") or {}
    code = int(_num(cur.get("weatherCode") if _naive(now).hour >= 18 else today.get("weatherCode"), 3))
    c = WMO.get(code, "cloudy")
    if c == "sunny" and is_night(data, _naive(now)):
        c = "night"
    th = thresholds(data)
    if _num(today.get("tempMax"), -99) >= th["heat_c"] and code <= 3:
        return "heat"
    if max_gust(data, now) >= th["wind_gust_kmh"] and c not in ("heavy", "thunder", "snow"):
        return "wind"
    if _num(today.get("tempMin"), 99) <= th["frost_c"] and code <= 3 and _naive(now).hour < 12:
        return "frost"
    return c


def hour_condition(data: dict, dt: datetime, e: dict) -> str:
    code = int(_num(e.get("weatherCode"), 3))
    c = WMO.get(code, "cloudy")
    night = (not e["isDay"]) if e.get("isDay") is not None else is_night(data, dt)
    th = thresholds(data)
    temp = _num(e.get("temperature"))
    if code <= 3 and temp >= th["heat_c"] and not night:
        return "heat"
    if _num(e.get("windGusts")) >= th["wind_gust_kmh"] and c not in ("heavy", "thunder", "snow"):
        return "wind"
    if code <= 3 and temp <= th["frost_c"]:
        return "frost"
    if c in ("sunny", "partly") and night:
        return "night"
    return c


def day_condition(data: dict, d: dict) -> str:
    code = int(_num(d.get("weatherCode"), 3))
    c = WMO.get(code, "cloudy")
    th = thresholds(data)
    if _num(d.get("tempMax"), -99) >= th["heat_c"] and code <= 3:
        return "heat"
    if _num(d.get("windGustsMax")) >= th["wind_gust_kmh"] and c not in ("heavy", "thunder", "snow"):
        return "wind"
    if _num(d.get("tempMin"), 99) <= th["frost_c"] and code <= 3:
        return "frost"
    return c


def first_rain(data: dict, now: datetime, count: int | None = None, today_only: bool = True) -> datetime | None:
    for dt, e in hours_from(data, now, count, today_only):
        if _num(e.get("precipProb")) >= 50:
            return dt
    return None


def uv_label(uv) -> str:
    u = r(uv)
    band = "LOW" if u <= 2 else "MOD" if u <= 5 else "HIGH" if u <= 7 else "V.HIGH" if u <= 10 else "EXTREME"
    return f"{u} {band}"


def moon_phase(d: date) -> str:
    """Worked out locally from a known new moon (6 Jan 2000 18:14 UTC)."""
    days = (datetime(d.year, d.month, d.day, 12) - datetime(2000, 1, 6, 18, 14)).total_seconds() / 86400
    age = days % 29.530588853
    names = ["NEW", "WAXING", "FIRST QTR", "WAXING", "FULL", "WANING", "LAST QTR", "WANING", "NEW"]
    return names[int((age / 29.530588853) * 8 + 0.5)]


def _cell(kind: str, data: dict, now: datetime) -> tuple[str, str]:
    today, cur = data.get("today") or {}, data.get("current") or {}
    hrs = hours_from(data, now, today_only=True)
    if kind == "uv":
        return "UV", uv_label(today.get("uvIndexMax"))
    if kind == "sunset":
        return "SUNSET", today.get("sunset") or "—"
    if kind == "sunrise":
        later = _naive(now).time() >= (_hm(today.get("sunset")) or time(18))
        return "SUNRISE", (data.get("tomorrowSunrise") if later else None) or today.get("sunrise") or "—"
    if kind == "moon":
        return "MOON", moon_phase(_naive(now).date())
    if kind == "feels":
        return "FEELS LIKE", deg(cur.get("apparentTemperature", cur.get("temperature")))
    if kind == "feels_min":
        vals = [_num(e["apparentTemperature"]) for _, e in hrs if e.get("apparentTemperature") is not None]
        v = today.get("apparentTempMin")
        if v is None:
            v = min(vals) if vals else cur.get("apparentTemperature", today.get("tempMin"))
        return "FEELS LIKE", deg(v)
    if kind == "visibility":
        vis = [_num(e["visibility"]) for _, e in hrs if e.get("visibility") is not None]
        v = min(vis) if vis else _num(cur.get("visibility"), 0)
        return "VISIBILITY", f"{r(v / 1000)} KM" if v >= 1000 else f"{int(round(v / 10) * 10)} M"
    if kind == "clears":
        seen_low = False
        for dt, e in hours_from(data, now):
            if e.get("visibility") is None:
                continue
            if _num(e["visibility"]) <= 1000:
                seen_low = True
            elif seen_low or dt > _naive(now):
                return "CLEARS", f"{dt:%H}:00"
        return "CLEARS", "LATER"
    if kind == "rainfall":
        return "RAINFALL", f"{r(today.get('precipSum'))} MM"
    if kind == "gusts":
        return "GUSTS", f"{r(max_gust(data, now))} KM/H"
    if kind == "snowfall":
        return "SNOWFALL", f"{r(today.get('snowfallSum'))} CM"
    if kind == "pavements":
        return "PAVEMENTS", "ICY" if _num(today.get("tempMin"), 9) <= (34 if data.get("units") == "F" else 1) else "WET"
    if kind == "thaw":
        frz = 32 if data.get("units") == "F" else 0
        for dt, e in hours_from(data, now, today_only=True):
            if _num(e.get("temperature")) > frz:
                return "THAW BY", f"{dt:%H}:00"
        return "THAW BY", "NOT TODAY"
    return kind.upper(), "—"


def details(cond: str, data: dict, now: datetime) -> list[tuple[str, str]]:
    today, cur = data.get("today") or {}, data.get("current") or {}
    a, b = CELLS[cond]
    return [("CHANCE OF RAIN", f"{r(today.get('precipProbMax'))}%"),
            ("WIND", f"{r(cur.get('windSpeed'))} km/h"),
            _cell(a, data, now), _cell(b, data, now)]


def sentence(cond: str, data: dict, now: datetime) -> str:
    rain = first_rain(data, now)
    if rain is not None and cond not in WET:
        return f"Rain from {rain:%H}:00."
    if cond == "rain":
        return f"Rain from {rain:%H}:00, easing tonight." if rain else "Rain on and off today."
    if cond == "wind":
        return SENTENCE["wind"].format(gust=r(max_gust(data, now)))
    if cond == "heat":
        hs = hours_from(data, now.replace(hour=0), today_only=True) or hours_from(data, now)
        peak = max(hs, key=lambda p: _num(p[1].get("temperature")))[0] if hs else None
        return f"Hot and sunny. Peak at {peak:%H}:00." if peak else "Hot and sunny."
    return SENTENCE[cond]


def tip(cond: str, data: dict) -> str:
    if cond == "sunny":
        return "SUNSCREEN ON" if r((data.get("today") or {}).get("uvIndexMax")) >= 3 else "ENJOY THE SUN"
    return TIP[cond]


def slot_times(cond: str, now: datetime) -> list[datetime]:
    n = _naive(now)
    if cond == "night":
        base = datetime.combine(n.date() - timedelta(days=1) if n.hour < 12 else n.date(), time(21))
        return [base + timedelta(hours=3 * i) for i in range(5)]
    return [datetime.combine(n.date(), time(h)) for h in (9, 12, 15, 18, 21)]


# ------------------------------------------------------------- templates --
def _place_row(data: dict, right: str) -> Row:
    left = (data.get("place") or "").split(",")[0]
    if data.get("staleFrom"):
        left = f"{left} · data from {data['staleFrom']}"
    return Row((Text(left, T.PX, max_lines=1), "flex"), (Text(right, T.PX_B), "auto"), gap=10)


def briefing(data: dict, now: datetime) -> list:
    """Section 5.2. One of 14 condition layouts."""
    cond = condition(data, now)
    today, cur = data.get("today") or {}, data.get("current") or {}
    cells = [Col(Text(k, T.PX), Text(v, T.T_L, max_lines=2), gap=2) for k, v in details(cond, data, now)]
    slots = []
    for when in slot_times(cond, now):
        e = at_hour(data, when) or {}
        slots.append(Col(Text(f"{when:%H}:00", T.PX(track=0)), Icon(hour_condition(data, when, e), 44),
                         Text(deg(e.get("temperature")), T.T_M), gap=4, align="center"))
    return [
        Header("WEATHER", dt_label(now)),
        _place_row(data, "TONIGHT" if cond == "night" else "TODAY"),
        Rule("hr2"),
        Pad(Col(Icon(cond, 168), align="center"), t=6, b=2),
        Text(T.CONDITIONS[cond], T.T_XL, align="center"),
        Text(sentence(cond, data, now), T.T_M, align="center", max_lines=2).m(-6),
        Pad(Row(Text(deg(cur.get("temperature")), T.T_XXL),
                Col(Text(f"H {deg(today.get('tempMax'))}", T.T_L), Text(f"L {deg(today.get('tempMin'))}", T.T_L), gap=6),
                gap=18, justify="center"), t=4, b=4),
        Rule("hr"),
        Grid(cells, 2, colgap=16, rowgap=12),
        Rule("hr"),
        Grid(slots, 5, colgap=4),
        Band(Text(tip(cond, data), T.T_L, align="center", max_lines=2), (8, 8, 8, 8)),
    ]


def _cols(w: int, n: int, gap: int) -> list[tuple[int, int]]:
    avail = w - gap * (n - 1)
    out, x = [], 0
    for i in range(n):
        cw = avail // n + (1 if i < avail % n else 0)
        out.append((x, cw))
        x += cw + gap
    return out


def _temp_chart(hours: list[tuple[datetime, dict]]) -> Custom:
    temps = [r(e.get("temperature")) for _, e in hours]
    lo, hi = (min(temps), max(temps)) if temps else (0, 0)

    def draw(c, x, y, w, h, ink):
        base = y + 112 - 3
        c.rect(x, base, x + w, base + 3, ink)
        for (cx, cw), t in zip(_cols(w, len(temps), 3), temps):
            bh = 34 if hi == lo else round(17 + (t - lo) / (hi - lo) * 68)
            c.rect(x + cx, base - bh, x + cx + cw, base, ink)
            Text(str(t), T.CHART, align="center").draw(c, x + cx - 3, base - bh - 2 - T.CHART.lh, cw + 6, T.CHART.lh, ink)

    return Custom(112, draw)


def _rain_chart(hours: list[tuple[datetime, dict]]) -> Custom:
    rains = [max(0, min(100, r(e.get("precipProb")))) for _, e in hours]

    def draw(c, x, y, w, h, ink):
        c.rect(x, y, x + w, y + 3, ink)
        for (cx, cw), p in zip(_cols(w, len(rains), 3), rains):
            bh = round(p * 0.75)
            top = y + 3
            if bh > 0:
                c.tone("d50", x + cx, top, cw, bh, ink)
                c.rect(x + cx, top, x + cx + 2, top + bh, ink)
                c.rect(x + cx + cw - 2, top, x + cx + cw, top + bh, ink)
                c.rect(x + cx, top + max(0, bh - 2), x + cx + cw, top + bh, ink)
            else:
                c.rect(x + cx, top, x + cx + cw, top + 2, ink)
            Text(str(p), T.CHART, align="center").draw(c, x + cx - 3, top + max(bh, 2) + 2, cw + 6, T.CHART.lh, ink)

    return Custom(104, draw)


def _hour_labels(hours) -> Custom:
    labels = [f"{dt:%H}" for dt, _ in hours]
    st = T.PX(track=0)

    def draw(c, x, y, w, h, ink):
        for (cx, cw), s in zip(_cols(w, len(labels), 3), labels):
            Text(s, st, align="center").draw(c, x + cx - 2, y, cw + 4, st.lh, ink)

    return Custom(st.lh, draw)


def week_summary(data: dict) -> str:
    days = (data.get("daily") or [])[:4]
    if not days:
        return ""
    parts = []
    cold = min(days, key=lambda d: _num(d.get("tempMin"), 99))
    parts.append(f"Coldest night {_day(cold).title()}, {deg(cold.get('tempMin'))}.")
    frz = 32 if data.get("units") == "F" else 0
    frost = next((d for d in days if _num(d.get("tempMin"), 99) <= frz), None)
    if frost:
        parts.append(f"Frost likely {_day_long(frost)} morning.")
    windy = max(days, key=lambda d: _num(d.get("windGustsMax")))
    if _num(windy.get("windGustsMax")) >= thresholds(data)["wind_gust_kmh"]:
        parts.append(f"Windiest {_day(windy).title()}, gusts {r(windy['windGustsMax'])} km/h.")
    return " ".join(parts)


def _day(d: dict) -> str:
    if d.get("day"):
        return str(d["day"]).upper()[:3]
    try:
        return date.fromisoformat(d["date"]).strftime("%a").upper()
    except (KeyError, ValueError):
        return "—"


def _day_long(d: dict) -> str:
    try:
        return date.fromisoformat(d["date"]).strftime("%A")
    except (KeyError, ValueError):
        return _day(d).title()


def weather_now(data: dict, now: datetime) -> list:
    """Section 6: today in a heavy box, next 12 hours, rest of the week."""
    cond = condition(data, now)
    today, cur = data.get("today") or {}, data.get("current") or {}
    hours = hours_from(data, now, 12)
    rain = first_rain(data, now, 12, today_only=False)
    if rain is not None:
        h12 = rain.hour % 12 or 12
        headline = f"RAIN AT {h12}"
        tip_text = f"LEAVE BEFORE {(rain - timedelta(minutes=30)):%H:%M}"
    else:
        headline = T.CONDITIONS[cond]
        tip_text = tip(cond, data)
    summary = f"{sentence(cond, data, now)} Wind {r(cur.get('windSpeed'))} km/h."
    n = _naive(now)
    inner = [
        Row(Icon(cond, 104), Col(Text(deg(cur.get("temperature")), T.T_XXL),
                                 Text(f"H {deg(today.get('tempMax'))} · L {deg(today.get('tempMin'))}", T.T_L), gap=6),
            gap=14),
        Text(headline, T.T_XL),
        Text(summary, T.T_M, max_lines=3),
    ]
    if hours:
        inner += [Rule("hr"), Text("NEXT 12 HOURS · TEMPERATURE °C", T.PX), _temp_chart(hours), _hour_labels(hours),
                  Text("CHANCE OF RAIN %", T.PX).m(2), _rain_chart(hours)]
    inner.append(Band(Text(tip_text, T.T_L, align="center", max_lines=2), (8, 8, 8, 8)))
    today_box = Box(Col(
        Band(Row((Text("TODAY", T.PX_B), "auto"), (Text(f"{n:%A} {n.day}", T.PX_B, align="right"), "flex")),
             (8, 12, 8, 12)),
        Pad(Col(*inner, gap=10), 14, 14, 16, 14),
    ), border=4, pad=0)
    blocks = [Header("WEATHER NOW", dt_label(now)), _place_row(data, ""), today_box]
    days = (data.get("daily") or [])[:4]
    if days:
        blocks.append(SectionRule("REST OF THE WEEK").m(4))
        for d in days:
            p = r(d.get("precipProbMax"))
            blocks.append(Col(
                Row((Text(_day(d), T.T_L), 52), (Icon(day_condition(data, d), 40), 40),
                    (Pad(Text(f"{deg(d.get('tempMax'))} / {deg(d.get('tempMin'))}", T.T_MB), l=4), "flex"),
                    (Col(Meter(p), Text(f"Rain {p}%", T.CHART), gap=3), 92), gap=10),
                Rule("hrd"), gap=8))
        s = week_summary(data)
        if s:
            blocks.append(Text(s, T.T_S))
    return blocks


def unavailable(now: datetime, title: str = "WEATHER", last: str | None = None) -> list:
    """Provider down and no recent forecast (BUILD_PLAN 7)."""
    lines = [Header(title, dt_label(now)), Rule("hr2"), Text("WEATHER UNAVAILABLE", T.T_XL, align="center"),
             Text("Can't reach the weather service.", T.T_M, align="center").m(-6)]
    if last:
        lines.append(Text(f"Last forecast: {last}", T.T_S, align="center"))
    return lines
