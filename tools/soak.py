#!/usr/bin/env python3
"""24-hour soak test against a running printer (BUILD_PLAN Phase 8).

    python3 tools/soak.py --base http://walloftext.local --password root --hours 24

What it does:
  * creates 24 hourly schedules named "Soak HH:05" (a short fortune each), so the scheduler fires
    every hour;
  * sends a small manual print every 15 minutes;
  * every minute records the service's health: /api/device temperature and throttling, queue length,
    and (when run on the Pi itself) the service's memory and restart count from systemd;
  * at the end removes the soak schedules and prints a report: expected vs printed, failures,
    restarts, memory growth, max temperature.
Needs paper: about 40 short slips (~1.5 m). Stop early with Ctrl-C; the report still prints.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://walloftext.local")
ap.add_argument("--password", default="root")
ap.add_argument("--hours", type=float, default=24)
ap.add_argument("--manual-every", type=float, default=15, help="minutes between manual prints")
args = ap.parse_args()

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method: str, path: str, body=None):
    data = json.dumps(body if body is not None else {}).encode() if method != "GET" else None
    req = urllib.request.Request(args.base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=20) as r:
        return json.loads(r.read() or b"{}")


def systemd(prop: str) -> str | None:
    try:
        out = subprocess.run(["systemctl", "show", "walloftext", "-p", prop, "--value"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


call("POST", "/api/auth/login", {"password": args.password, "remember": True})
start = time.time()
end = start + args.hours * 3600
created = []
for h in range(24):
    s = call("POST", "/api/schedules", {"name": f"Soak {h:02d}:05", "time": f"{h:02d}:05",
                                        "days": list(range(7)), "sections": [{"type": "fortune"}]})
    created.append(s["id"])
print(f"soak: {len(created)} schedules created; running {args.hours} h")
mem0 = systemd("MemoryCurrent")
restarts0 = systemd("NRestarts")
samples, manual, errors = [], 0, []
last_manual = 0.0
try:
    while time.time() < end:
        now = time.time()
        try:
            if now - last_manual >= args.manual_every * 60:
                call("POST", "/api/print", {"document": {"blocks": [
                    {"type": "text", "text": f"Soak {time.strftime('%H:%M')}", "size": "S"}]}, "title": "Soak manual"})
                manual += 1
                last_manual = now
            d = call("GET", "/api/device")
            samples.append({"t": now, "temp": d.get("temperature_c"), "flags": d["throttled"]["flags"],
                            "queue": d["printer"]["queue_length"], "state": d["printer"]["state"],
                            "mem": systemd("MemoryCurrent")})
        except (urllib.error.URLError, OSError, KeyError) as exc:
            errors.append(f"{time.strftime('%H:%M:%S')} {exc}")
        time.sleep(60)
except KeyboardInterrupt:
    print("soak: stopped early")
finally:
    hist = call("GET", "/api/history?limit=500")["items"]
    since = [j for j in hist if j["created_at"] >= start]
    sched = [j for j in since if j["source"] == "Schedule"]
    for sid in created:
        try:
            call("DELETE", f"/api/schedules/{sid}")
        except Exception:
            pass
    hours = (time.time() - start) / 3600
    temps = [s["temp"] for s in samples if s["temp"] is not None]
    mems = [int(s["mem"]) for s in samples if s["mem"] and s["mem"].isdigit()]
    report = {
        "hours": round(hours, 2),
        "manual_sent": manual,
        "scheduled_expected_about": int(hours),
        "scheduled_printed": sum(1 for j in sched if j["state"] == "done"),
        "missed": [j["title"] for j in since if j["state"] == "missed"],
        "failed": [(j["title"], j["error"]) for j in since if j["state"] == "failed"],
        "max_temp_c": max(temps) if temps else None,
        "throttle_flags_seen": sorted({f for s in samples for f in s["flags"]}),
        "max_queue": max((s["queue"] for s in samples), default=0),
        "memory_start_mb": round(int(mem0) / 1e6, 1) if mem0 and mem0.isdigit() else None,
        "memory_end_mb": round(mems[-1] / 1e6, 1) if mems else None,
        "service_restarts": (int(systemd("NRestarts") or 0) - int(restarts0 or 0)) if restarts0 else None,
        "request_errors": errors[-10:],
    }
    print(json.dumps(report, indent=1))
    ok = not report["failed"] and not report["service_restarts"]
    sys.exit(0 if ok else 1)
