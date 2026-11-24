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
                "rotate_180": True,
                "default_font": "mono", "default_size": "M", "cut_lines": 3,
                "roll_length_m": 10.0, "mm_per_row": 0.125},  # paper estimate: roll length, calibrated row pitch
    "schedules": {"timezone": "Europe/London", "missed_policy": "late_60",  # late_60 | skip | always | notice
                  "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:30"},
                  "holiday_mode": False, "daily_limit": 30},
    "history": {"max_items": 200, "max_days": 30},  # 0 = no limit
    "fortunes": {"use_builtin": True},
    "weather": {"place": "", "lat": None, "lon": None, "units": "C"},
    # Google Calendar and Tasks (sources/google.py). Empty = the main calendar / the first task list.
    "google": {"calendars": [], "task_lists": []},  # calendars: [{id, name}], task_lists: [id]
    "button": {"single": "reprint_last", "double": "weather_now", "long": "agenda_today"},
    "led": {"brightness": 60,
            "patterns": {"idle": "off", "printing": "blink", "message_waiting": "slow_pulse",
                         "paper_out": "solid", "error": "blink"}},
    "guest": {"enabled": False, "mode": "approve",  # approve | print
              "max_chars": 280, "rate_per_10min": 5},
    "remote": {"max_chars": 600, "max_lines": 40, "rate_per_hour": 10, "ack_email": False},
    "display": {"reduce_motion": False, "reduce_transparency": False, "sounds": False},
    # Scheduled backup to a USB drive: daily | weekly | monthly (the 1st) at `time`; weekly on `weekday` (0 = Mon)
    "backup": {"usb_enabled": False, "frequency": "weekly", "time": "03:00", "weekday": 6, "keep": 10},
}


_UNSET = object()


def _merge(base: Any, over: Any, default: Any = _UNSET) -> Any:
    """Overlay `over` on `base`, keeping base's shape. `default` is the matching DEFAULTS
    value: a key whose default is None (e.g. lat/lon) may be set back to None."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for k, v in over.items():
            if k in base:
                d = default.get(k, _UNSET) if isinstance(default, dict) else _UNSET
                out[k] = _merge(base[k], v, d)
        return out
    if isinstance(base, list):
        return over if isinstance(over, list) else base
    if over is None:
        return None if (base is None or default is None) else base
    if base is None or default is None or isinstance(over, type(base)) or (
            isinstance(base, (int, float)) and isinstance(over, (int, float)) and not isinstance(over, bool)):
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
        return _merge(DEFAULTS, saved, DEFAULTS)

    def get(self, group: str) -> Any:
        return self.all()[group]

    def patch(self, changes: dict) -> dict:
        with self._lock:
            merged = _merge(self.all(), changes, DEFAULTS)
            self.store.set(self.KEY, json.dumps(merged))
        for cb in self.listeners:
            cb(merged)
        return merged

    def replace_group(self, group: str, value: Any) -> dict:
        return self.patch({group: value})
