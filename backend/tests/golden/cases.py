"""Golden documents: every template, empty state and edge case (IMPLEMENTATION_BRIEF WP7).

Each case is a full print document. `tools/update_goldens.py` renders them into
`tests/golden/*.png` on purpose; `tests/test_goldens.py` checks nothing drifted.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[3] / "print-templates" / "samples"


def sample(name: str) -> dict:
    d = json.loads((SAMPLES / f"{name}.json").read_text())
    d.pop("_comment", None)
    return d


def slip(template: str, data: dict) -> dict:
    return {"blocks": [{"type": "slip", "template": template, "data": data}]}


# --------------------------------------------------------------- weather --
# The D table in print-templates/reference/Weather.dc.html, turned back into provider data:
# (today code, date, print time, t, hi, lo, rain %, wind, gust max, slot temps, slot codes, extras)
D = {
    "sunny": (0, "2026-06-06", "07:30", 18, 21, 11, 0, 8, 20, [15, 19, 21, 18, 14], [0, 0, 0, 0, 0],
              {"uvIndexMax": 5, "sunset": "21:12", "sunrise": "04:43"}),
    "night": (0, "2026-11-23", "21:30", 6, 11, 2, 0, 5, 12, [6, 4, 3, 2, 5], [0, 0, 0, 0, 0],
              {"sunrise": "07:21"}),
    "partly": (2, "2026-05-14", "07:30", 14, 16, 8, 10, 14, 30, [11, 14, 16, 13, 10], [1, 2, 2, 3, 0],
               {"uvIndexMax": 3, "sunset": "20:32", "sunrise": "05:10"}),
    "cloudy": (3, "2026-11-23", "07:30", 11, 12, 7, 20, 12, 25, [9, 11, 12, 10, 8], [3, 3, 3, 3, 3], {}),
    "fog": (45, "2026-11-23", "07:30", 5, 8, 3, 10, 4, 10, [3, 6, 8, 6, 4], [45, 45, 2, 3, 45], {}),
    "drizzle": (53, "2026-11-23", "07:30", 10, 11, 7, 40, 15, 30, [8, 10, 11, 9, 8], [53, 53, 3, 53, 3], {}),
    "rain": (63, "2026-11-23", "07:30", 9, 10, 6, 80, 20, 34, [8, 9, 10, 8, 7], [3, 3, 63, 63, 53],
             {"precipSum": 6.2}),
    "heavy": (65, "2026-11-23", "07:30", 8, 9, 6, 95, 30, 45, [7, 8, 9, 8, 7], [63, 65, 65, 65, 63],
              {"precipSum": 24}),
    "thunder": (95, "2026-08-12", "07:30", 22, 25, 15, 85, 35, 59, [20, 24, 25, 21, 17], [2, 3, 95, 95, 63],
                {"precipSum": 18, "sunset": "20:31", "sunrise": "05:50"}),
    "snow": (73, "2027-01-12", "07:30", 0, 1, -3, 70, 18, 30, [-1, 0, 1, -1, -2], [73, 73, 3, 73, 0],
             {"snowfallSum": 3, "sunrise": "08:02", "sunset": "16:20"}),
    "sleet": (66, "2027-01-22", "07:30", 2, 3, 0, 75, 28, 45, [1, 2, 3, 1, 0], [3, 66, 66, 63, 0],
              {"sunrise": "07:52", "sunset": "16:35"}),
    "frost": (0, "2026-11-27", "07:30", -2, 4, -4, 0, 6, 12, [-2, 2, 4, 1, -3], [0, 2, 0, 0, 0], {}),
    "wind": (3, "2026-11-23", "07:30", 12, 13, 9, 30, 55, 80, [11, 12, 13, 12, 10], [3, 3, 3, 3, 3], {}),
    "heat": (0, "2026-07-18", "07:30", 32, 34, 21, 0, 10, 20, [26, 31, 34, 31, 25], [0, 0, 0, 0, 0],
             {"uvIndexMax": 9, "sunset": "21:17", "sunrise": "05:02"}),
}
FEELS = {"cloudy": 9, "drizzle": 7, "snow": -5, "sleet": -3, "frost": -6, "wind": 8}


def weather_case(cond: str) -> dict:
    code, day, at, t, hi, lo, rain, wind, gust, temps, codes, extra = D[cond]
    hours = (21, 24, 27, 30, 33) if cond == "night" else (9, 12, 15, 18, 21)
    hourly = []
    from datetime import date, timedelta

    d0 = date.fromisoformat(day) - timedelta(days=1 if cond == "night" and int(at[:2]) < 12 else 0)
    for h in range(0, 36):
        # temperatures and codes held from the nearest slot
        k = min(range(5), key=lambda i: abs(hours[i] - h))
        prob = 0
        if cond in ("rain", "heavy", "thunder", "drizzle", "snow", "sleet"):
            prob = rain if h >= (14 if cond == "rain" else 9) else 20
        vis = 150 if cond == "fog" and h < 11 else 20000
        hourly.append({"date": (d0 + timedelta(days=h // 24)).isoformat(), "time": f"{h % 24:02d}:00",
                       "temperature": temps[k], "precipProb": prob, "weatherCode": codes[k], "visibility": vis,
                       "windGusts": gust if cond == "wind" else min(gust, 40),
                       "apparentTemperature": FEELS.get(cond, temps[k]) if cond == "frost" and h < 9 else temps[k] - 2})
    today = {"date": day, "tempMax": hi, "tempMin": lo, "precipProbMax": rain, "precipSum": 0, "snowfallSum": 0,
             "uvIndexMax": 1, "weatherCode": code, "sunrise": "07:31", "sunset": "16:05", "windGustsMax": gust}
    today.update(extra)
    if cond == "frost":
        today["apparentTempMin"] = -6
    return slip("weather_briefing", {
        "place": "London", "units": "C", "now": f"{day}T{at}",
        "current": {"temperature": t, "apparentTemperature": FEELS.get(cond, t - 2), "weatherCode": code,
                    "windSpeed": wind, "windGusts": gust, "visibility": 20000},
        "today": today, "hourly": hourly, "daily": []})


def cases() -> dict[str, dict]:
    out: dict[str, dict] = {}
    w = sample("weather")
    out["weather_briefing_sample"] = slip("weather_briefing", dict(w, now="2026-11-23T07:30"))
    out["weather_now_sample"] = slip("weather_now", dict(w, now="2026-11-23T08:00"))
    for cond in D:
        out[f"weather_{cond}"] = weather_case(cond)
    # edge cases: negative temperatures, a 0 % and a 100 % rain day
    cold = copy.deepcopy(w)
    cold["current"]["temperature"] = -12
    cold["today"].update(tempMax=-8, tempMin=-15, precipProbMax=0)
    for h in cold["hourly"]:
        h.update(temperature=h["temperature"] - 20, precipProb=0, weatherCode=0)
    out["weather_now_negative_dry"] = slip("weather_now", dict(cold, now="2026-11-23T08:00"))
    wet = copy.deepcopy(w)
    wet["today"]["precipProbMax"] = 100
    for h in wet["hourly"]:
        h.update(precipProb=100, weatherCode=65)
    for d in wet["daily"]:
        d["precipProbMax"] = 100
    out["weather_now_all_rain"] = slip("weather_now", dict(wet, now="2026-11-23T08:00"))
    out["weather_unavailable"] = slip("unavailable", {"source": "WEATHER", "title": "Weather unavailable",
                                                      "text": "Can't reach the weather service.",
                                                      "last": "Mon 06:58", "now": "2026-11-23T07:30"})

    t = sample("tasks")
    out["todo_sample"] = slip("todo", dict(t, now="2026-11-23T07:30"))
    clear = copy.deepcopy(t)
    clear["today"] = "2026-11-28"
    clear["tasks"] = [x for x in clear["tasks"] if not x["due"] or x["due"] > "2026-11-28"] + [
        {"id": "x1", "list": "Home", "order": 20, "title": "Defrost the freezer", "notes": "", "due": "2026-12-02",
         "parent": None},
        {"id": "x2", "list": "Home", "order": 21, "title": "Send rent", "notes": "", "due": "2026-12-08",
         "parent": None}]
    out["todo_all_clear"] = slip("todo", dict(clear, now="2026-11-28T07:30"))
    many = copy.deepcopy(t)
    many["tasks"] += [{"id": f"m{i}", "list": "Errands", "order": 30 + i,
                       "title": ("A forty character task title, quite long" if i == 0 else f"Extra task {i}"),
                       "notes": "", "due": "2026-11-23" if i < 4 else None, "parent": None} for i in range(10)]
    many["tasks"][0]["title"] = "Call landlord about the boiler and the window @10:00"
    many["tasks"][0]["notes"] = "Ask for Thursday. Also mention the damp patch in the hall and the extractor fan."
    out["todo_many"] = slip("todo", dict(many, now="2026-11-23T07:30"))

    cal = sample("calendar")
    out["itinerary_sample"] = slip("itinerary", dict(cal, now="2026-11-23T07:30"))
    out["itinerary_free"] = slip("itinerary", {"date": "2026-11-28", "events": [], "allDay": [],
                                               "nextEvent": {"title": "Team stand-up", "date": "2026-11-30",
                                                             "start": "09:30"}, "now": "2026-11-28T07:30"})
    out["itinerary_free_none"] = slip("itinerary", {"date": "2026-11-28", "events": [], "allDay": [],
                                                    "nextEvent": None, "now": "2026-11-28T07:30"})
    busy = copy.deepcopy(cal)
    busy["allDay"] += [{"title": "Bank holiday"}, {"title": "Sam's birthday"}, {"title": "Bins"}]
    busy["events"] += [
        {"uid": "e6", "title": "Overlapping call with the very long title here", "start": "11:30", "end": "12:00",
         "location": "", "conferenceUrl": "https://zoom.us/j/123456789", "attendees": ["Ana", "Tom", "Ravi"],
         "description": "Line one.\nLine two.\nLine three.\nLine four is cut.", "calendar": "Work"},
        {"uid": "e7", "title": "Gym", "start": "07:00", "end": "08:00", "location": "", "conferenceUrl": None,
         "attendees": [], "description": "", "calendar": "Personal"},
        {"uid": "e8", "title": "School run", "start": "08:15", "end": "08:45", "location": "", "conferenceUrl": None,
         "attendees": [], "description": "", "calendar": "Personal"},
        {"uid": "e9", "title": "Late film", "start": "22:30", "end": "01:00", "endDate": "2026-11-24",
         "location": "Picturehouse, 1 Market Square", "conferenceUrl": None, "attendees": [], "description": "",
         "calendar": "Personal"}]
    out["itinerary_nine_overlap_midnight"] = slip("itinerary", dict(busy, now="2026-11-23T11:40"))

    out["note"] = slip("note", {"text": "Back at 7. Pasta's in the fridge, help yourself.\nBins go out tonight.",
                                "now": "2026-11-23T18:42"})
    out["note_long"] = slip("note", {"text": "A note long enough to wrap onto three lines of the big type size here."
                                             "\nSecond line.\nThird line.", "now": "2026-11-23T18:42"})
    out["guest_note"] = slip("guest_note", {"name": "Sam", "text": "Thanks for dinner!", "sticker": "heart",
                                            "now": "2026-11-23T21:05"})
    out["message"] = slip("message", {"sender": "Ana", "subject": "Spare keys",
                                      "body": "I left the spare keys with the neighbour at no. 14. Back on Sunday, "
                                              "water the basil please!", "now": "2026-11-23T18:42"})
    out["shopping"] = slip("shopping", {"items": ["Oat milk", "Eggs ×6", "Halloumi", "Coffee beans", "Rice",
                                                  "Bin bags", "Washing-up liquid"], "now": "2026-11-26T18:00"})
    out["fortune"] = slip("fortune", {"text": "A small kindness comes back to you today.", "lucky": 17,
                                      "now": "2026-11-24T22:10"})
    out["quote"] = slip("fortune", {"label": "QUOTE", "text": "Be kind.", "now": "2026-11-24T22:10"})
    out["countdown"] = slip("countdown", {"date": "2026-12-04", "label": "the holiday", "set_on": "2026-10-19",
                                          "tip": "START PACKING SATURDAY", "now": "2026-11-23T08:00"})
    out["test_page"] = slip("test_page", {"paper": "About 60%", "darkness": "Normal", "speed": "Normal",
                                          "address": "walloftext.local", "now": "2026-11-23T12:04"})
    out["routine"] = {"blocks": [out["weather_briefing_sample"]["blocks"][0], {"type": "cut"},
                                 out["todo_sample"]["blocks"][0], {"type": "cut"},
                                 {"type": "group", "blocks": [{"type": "text", "text": "Have a good day!"}]}]}
    out["create_text"] = {"blocks": [{"type": "heading", "text": "Hello"}, {"type": "text", "text": "A Create print"}]}
    return out
