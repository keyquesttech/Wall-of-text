"""Single place for names, paths and tunables.

Everything that may differ between the Pi and a dev PC is read from the
environment, so tests and `WOT_HW=mock` runs never touch /etc or /var.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Override 1: hostname and product name live here, so a rename is one line.
PRODUCT_NAME = "Wall Printer"
HOSTNAME = "walloftext"
LOCAL_ADDRESS = f"{HOSTNAME}.local"

SETUP_SSID = "WallOfText-Setup"
AP_ADDRESS = "10.42.0.1"
AP_CON_NAME = "wot-setup-ap"
CLIENT_CON_NAME = "wot-client"

DEFAULT_GUI_PASSWORD = "root"
DEFAULT_SETUP_WIFI_PASSWORD = "rootroot"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: str | Path) -> Path:
    return Path(os.environ.get(name, str(default)))


@dataclass
class Settings:
    hw: str = field(default_factory=lambda: os.environ.get("WOT_HW", "mock"))
    port: int = field(default_factory=lambda: int(os.environ.get("WOT_PORT", "8080")))
    password_file: Path = field(
        default_factory=lambda: _env_path("WOT_PASSWORD_FILE", REPO_ROOT / "backend/var/passwords.txt")
    )
    data_dir: Path = field(default_factory=lambda: _env_path("WOT_DATA_DIR", REPO_ROOT / "backend/var"))
    setup_ui_dir: Path = field(default_factory=lambda: _env_path("WOT_SETUP_UI", REPO_ROOT / "setup-ui"))
    frontend_dir: Path = field(default_factory=lambda: _env_path("WOT_FRONTEND", REPO_ROOT / "frontend/dist"))
    fonts_dir: Path = field(default_factory=lambda: _env_path("WOT_FONTS", REPO_ROOT / "fonts"))
    printer_device: str = field(default_factory=lambda: os.environ.get("WOT_PRINTER", "/dev/walloftext-printer"))
    button_pin: int = field(default_factory=lambda: int(os.environ.get("WOT_BUTTON_PIN", "17")))
    led_pin: int = field(default_factory=lambda: int(os.environ.get("WOT_LED_PIN", "18")))
    # Extra Host names accepted for mutating requests (dev: your PC's name for the Pi, e.g. an IP)
    extra_hosts: list[str] = field(default_factory=lambda: os.environ.get("WOT_EXTRA_HOSTS", "").split(","))
    # Wi-Fi state machine timings (section 5.1)
    connect_timeout_s: float = 120.0
    fallback_retry_s: float = 60.0
    link_lost_s: float = 300.0
    client_ip_wait_s: float = 30.0
    connect_reply_delay_s: float = 4.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "walloftext.db"

    @property
    def mock_printer_dir(self) -> Path:
        return self.data_dir / "mock-printer"

    @property
    def wifi_scan_cache(self) -> Path:
        return self.data_dir / "wifi-scan.json"

    @property
    def wifi_state_file(self) -> Path:
        return self.data_dir / "wifi-state.json"

    @property
    def is_mock(self) -> bool:
        return self.hw != "real"


def get_settings() -> Settings:
    return Settings()
