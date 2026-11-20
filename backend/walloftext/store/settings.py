"""User settings: one JSON document in the kv table, merged over defaults.

Groups mirror Settings in the UI. Unknown keys sent by a client are dropped.
"""
from __future__ import annotations

import copy
import json
import threading
from typing import Any

from .db import Store

DEFAULTS: dict[str, Any] = {
    "printer": {"darkness": 120, "speed": "normal", "band_rows": 24, "extra_feed": 0, "paper_saver": False,
                "default_font": "mono", "default_size": "M", "cut_lines": 3},
    "schedules": {"timezone": "Europe/London", "missed_policy": "late_60",  # late_60 | skip | always
                  "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:30"},
                  "holiday_mode": False, "daily_limit": 30},
    "history": {"max_items": 200, "max_days": 30},
    "weather": {"place": "", "lat": None, "lon": None, "units": "C"},
    "calendars": [],  # [{id, name, url}]
    "tasks": {"enabled": False, "lists": []},
    "button": {"single": "reprint_last", "double": "weather_now", "long": "agenda_today"},
    "led": {"brightness": 60,
            "patterns": {"idle": "off", "printing": "blink", "message_waiting": "slow_pulse",
                         "paper_out": "solid", "error": "blink"}},
    "guest": {"enabled": False, "mode": "approve",  # approve | print
              "max_chars": 280, "rate_per_10min": 5},
    "remote": {"max_chars": 600, "max_lines": 40, "rate_per_hour": 10, "ack_email": False},
    "display": {"reduce_motion": False, "reduce_transparency": False, "sounds": False},
}


def _merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for k, v in over.items():
            if k in base:
                out[k] = _merge(base[k], v)
        return out
    if isinstance(base, list):
        return over if isinstance(over, list) else base
    if base is None or isinstance(over, type(base)) or (isinstance(base, (int, float)) and isinstance(over, (int, float))):
        return over
    return base


class AppSettings:
    KEY = "app_settings"

    def __init__(self, store: Store):
        self.store = store
        self._lock = threading.Lock()
        self.listeners: list = []

    def all(self) -> dict:
        try:
            saved = json.loads(self.store.get(self.KEY, "{}") or "{}")
        except ValueError:
            saved = {}
        return _merge(DEFAULTS, saved)

    def get(self, group: str) -> Any:
        return self.all()[group]

    def patch(self, changes: dict) -> dict:
        with self._lock:
            merged = _merge(self.all(), changes)
            self.store.set(self.KEY, json.dumps(merged))
        for cb in self.listeners:
            cb(merged)
        return merged

    def replace_group(self, group: str, value: Any) -> dict:
        return self.patch({group: value})
