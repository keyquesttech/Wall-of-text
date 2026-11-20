"""System stats for Settings › Device (no fan state: override 5)."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

THROTTLE_BITS = {
    0: "under_voltage",
    1: "arm_freq_capped",
    2: "throttled",
    3: "soft_temp_limit",
    16: "under_voltage_since_boot",
    17: "arm_freq_capped_since_boot",
    18: "throttled_since_boot",
    19: "soft_temp_limit_since_boot",
}


def decode_throttled(value: int) -> list[str]:
    return [name for bit, name in THROTTLE_BITS.items() if value & (1 << bit)]


class SystemInfo:
    def temperature_c(self) -> float | None:
        try:
            return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        except (OSError, ValueError):
            return None

    def throttled(self) -> dict:
        try:
            out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5).stdout
            raw = int(out.strip().split("=")[1], 16)
        except (OSError, IndexError, ValueError, subprocess.SubprocessError):
            return {"raw": None, "flags": []}
        return {"raw": hex(raw), "flags": decode_throttled(raw)}

    def uptime_s(self) -> float:
        try:
            return float(Path("/proc/uptime").read_text().split()[0])
        except (OSError, ValueError):
            return time.monotonic()

    def disk(self) -> dict:
        u = shutil.disk_usage("/")
        return {"total": u.total, "free": u.free}

    def clock_synced(self) -> bool:
        try:
            out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                 capture_output=True, text=True, timeout=5).stdout
            return out.strip() == "yes"
        except (OSError, subprocess.SubprocessError):
            return False


class MockSystemInfo(SystemInfo):
    def temperature_c(self) -> float | None:
        return 47.2

    def throttled(self) -> dict:
        return {"raw": "0x0", "flags": []}

    def clock_synced(self) -> bool:
        return True
