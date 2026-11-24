"""Print kit: one renderer for every printed slip (PRINT_TEMPLATES.md).

`render_template(name, data)` turns normalised data into a 384-dot, 1-bit slip
(no end mark: the print pipeline adds one per printed copy).
"""
from __future__ import annotations

from datetime import datetime

from PIL import Image

from . import itinerary, system, todo, weather
from .slip import render_slip

TEMPLATES = {
    "weather_briefing": (weather.briefing, 14),
    "weather_now": (weather.weather_now, 14),
    "todo": (todo.todo, 12),
    "itinerary": (itinerary.itinerary, 14),
    "note": (system.note, 14),
    "guest_note": (system.guest_note, 14),
    "message": (system.message, 14),
    "shopping": (system.shopping, 12),
    "fortune": (system.fortune, 14),
    "countdown": (system.countdown, 14),
    "test_page": (system.test_page, 14),
    "calibration": (system.calibration, 14),
    "date": (system.date_slip, 14),
    "unavailable": (system.unavailable, 14),
}


def when(data: dict) -> datetime:
    """The print time: data["now"] (ISO, local wall time) or the clock."""
    try:
        return datetime.fromisoformat(data["now"]).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        return datetime.now()


def render_template(name: str, data: dict) -> Image.Image:
    if name not in TEMPLATES:
        raise KeyError(name)
    fn, gap = TEMPLATES[name]
    data = dict(data or {})
    src = data.pop("image_src", None)
    if src:
        from ..document import DocumentError, decode_image, process_image

        try:
            img = process_image(decode_image(src), style="photo", dither="floyd", width=344, lighten=True)
            data["image"] = img.crop((20, 0, 364, img.height))
        except DocumentError:
            pass
    return render_slip(fn(data, when(data)), gap=gap)
