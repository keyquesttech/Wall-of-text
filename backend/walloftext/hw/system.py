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


    # ---------------------------------------------------------- date and time --
    # The Pi 4 has no battery-backed clock. At boot systemd-timesyncd asks internet time servers
    # (NTP) for the time; until it answers, the clock is wrong after a power cut. These calls go
    # through systemd-timedated over D-Bus; deploy/polkit lets the walloftext user make them.
    def _timedatectl(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["timedatectl", "--no-ask-password", *args], capture_output=True, text=True, timeout=10)

    def time_status(self) -> dict:
        info: dict[str, str] = {}
        try:
            out = self._timedatectl("show").stdout
            info = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        except (OSError, subprocess.SubprocessError):
            pass
        return {"epoch": time.time(), "system_timezone": info.get("Timezone", ""),
                "ntp": info.get("NTP") == "yes", "synced": info.get("NTPSynchronized") == "yes",
                "can_ntp": info.get("CanNTP", "yes") == "yes"}

    def _run_or_raise(self, *args: str) -> None:
        r = self._timedatectl(*args)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "timedatectl failed").strip()[:200])

    def set_ntp(self, on: bool) -> None:
        self._run_or_raise("set-ntp", "true" if on else "false")

    def set_time(self, epoch: float) -> None:
        """Set the system clock (NTP must be off). timedatectl reads local time in the system zone."""
        self._run_or_raise("set-time", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch)))

    def set_timezone(self, tz: str) -> None:
        self._run_or_raise("set-timezone", tz)

    def boot_id(self) -> str:
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            return ""


class MockSystemInfo(SystemInfo):
    def temperature_c(self) -> float | None:
        return 47.2

    def throttled(self) -> dict:
        return {"raw": "0x0", "flags": []}

    def clock_synced(self) -> bool:
        return True

    # date and time: kept in memory so the settings page can be tried without root
    _ntp = True
    _offset = 0.0
    _tz = "Europe/London"

    def time_status(self) -> dict:
        return {"epoch": time.time() + self._offset, "system_timezone": self._tz, "ntp": self._ntp,
                "synced": self._ntp, "can_ntp": True}

    def set_ntp(self, on: bool) -> None:
        self._ntp = on
        if on:
            self._offset = 0.0

    def set_time(self, epoch: float) -> None:
        if self._ntp:
            raise RuntimeError("Automatic time is on")
        self._offset = epoch - time.time()

    def set_timezone(self, tz: str) -> None:
        self._tz = tz

    def boot_id(self) -> str:
        return "mock-boot"
