"""The plain-text password file (BUILD_PLAN section 10.1).

The file is plain text on purpose. It is re-read whenever its modification
time changes. Bad values are ignored and the last valid value stays in force.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import DEFAULT_GUI_PASSWORD, DEFAULT_SETUP_WIFI_PASSWORD

log = logging.getLogger(__name__)

HEADER = (
    "# Wall of Text passwords. Plain text on purpose: edit this file, or use Settings > Access.\n"
    "# Changes apply straight away. No restart needed.\n"
)

GUI_MIN, GUI_MAX = 4, 64
WIFI_MIN, WIFI_MAX = 8, 63


def validate_gui(value: str) -> str | None:
    if not value or value.strip() != value:
        return "The site password can't be blank or start or end with a space."
    if not GUI_MIN <= len(value) <= GUI_MAX:
        return f"The site password must be {GUI_MIN} to {GUI_MAX} characters."
    return None


def validate_wifi(value: str) -> str | None:
    if not value:
        return "The setup Wi-Fi password can't be blank."
    if not WIFI_MIN <= len(value) <= WIFI_MAX:
        return f"The setup Wi-Fi password must be {WIFI_MIN} to {WIFI_MAX} characters."
    if not all(32 <= ord(c) <= 126 for c in value):
        return "The setup Wi-Fi password can only use plain keyboard characters."
    return None


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value
    return out


@dataclass
class PasswordState:
    gui_password: str = DEFAULT_GUI_PASSWORD
    setup_wifi_password: str = DEFAULT_SETUP_WIFI_PASSWORD
    warnings: list[str] = field(default_factory=list)

    @property
    def default_gui(self) -> bool:
        return self.gui_password == DEFAULT_GUI_PASSWORD

    @property
    def default_wifi(self) -> bool:
        return self.setup_wifi_password == DEFAULT_SETUP_WIFI_PASSWORD


class PasswordFile:
    """Owns the password file. Thread-safe; cheap to call `refresh()` often."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.state = PasswordState()
        self._mtime: float | None = None
        self._lock = threading.Lock()
        self.on_gui_change: list[Callable[[], None]] = []
        self.on_wifi_change: list[Callable[[str], None]] = []
        self.refresh()

    # -- reading ---------------------------------------------------------
    def _stat_mtime(self) -> float | None:
        try:
            return self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def refresh(self) -> bool:
        """Re-read the file if it changed. Returns True when values changed."""
        with self._lock:
            mtime = self._stat_mtime()
            if mtime is None:
                log.warning("password file %s missing; recreating with defaults", self.path)
                self._write_locked(DEFAULT_GUI_PASSWORD, DEFAULT_SETUP_WIFI_PASSWORD)
                mtime = self._stat_mtime()
            if mtime == self._mtime:
                return False
            self._mtime = mtime
            try:
                values = parse(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                log.error("cannot read password file: %s", exc)
                self.state.warnings = ["The password file can't be read, so the old passwords are still in use."]
                return False
            old = PasswordState(self.state.gui_password, self.state.setup_wifi_password)
            warnings: list[str] = []
            gui = values.get("gui_password")
            if gui is None or validate_gui(gui):
                warnings.append(
                    "The site password in the file is missing or invalid, so the old one is still in use."
                )
                log.warning("password file: gui_password invalid, keeping previous value")
            else:
                self.state.gui_password = gui
            wifi = values.get("setup_wifi_password")
            if wifi is None or validate_wifi(wifi):
                warnings.append(
                    "The setup Wi-Fi password in the file is too short or invalid, so the old one is still in use."
                )
                log.warning("password file: setup_wifi_password invalid, keeping previous value")
            else:
                self.state.setup_wifi_password = wifi
            self.state.warnings = warnings
            gui_changed = old.gui_password != self.state.gui_password
            wifi_changed = old.setup_wifi_password != self.state.setup_wifi_password
        if gui_changed:
            for cb in self.on_gui_change:
                cb()
        if wifi_changed:
            for cb in self.on_wifi_change:
                cb(self.state.setup_wifi_password)
        return gui_changed or wifi_changed

    # -- writing ---------------------------------------------------------
    def _write_locked(self, gui: str, wifi: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = HEADER + f"gui_password={gui}\nsetup_wifi_password={wifi}\n"
        st = None
        try:
            st = self.path.stat()
        except FileNotFoundError:
            pass
        fd, tmp = tempfile.mkstemp(prefix=".passwords.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o600)
            if st is not None:
                try:
                    os.chown(tmp, st.st_uid, st.st_gid)
                except PermissionError:
                    pass
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def set_gui(self, value: str) -> None:
        err = validate_gui(value)
        if err:
            raise ValueError(err)
        with self._lock:
            self._write_locked(value, self.state.setup_wifi_password)
        self.refresh()

    def set_wifi(self, value: str) -> None:
        err = validate_wifi(value)
        if err:
            raise ValueError(err)
        with self._lock:
            self._write_locked(self.state.gui_password, value)
        self.refresh()

    def reset_defaults(self) -> None:
        with self._lock:
            self._write_locked(DEFAULT_GUI_PASSWORD, DEFAULT_SETUP_WIFI_PASSWORD)
        self.refresh()
