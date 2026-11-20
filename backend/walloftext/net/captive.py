"""Captive-portal probe handling (section 5.3). Active only in AP modes."""
from __future__ import annotations

from ..config import AP_ADDRESS

SETUP_URL = f"http://{AP_ADDRESS}/setup"

PROBE_PATHS = {
    "/hotspot-detect.html",  # Apple
    "/library/test/success.html",  # older Apple
    "/generate_204",  # Android / Chrome
    "/gen_204",
    "/connecttest.txt",  # Windows 10+
    "/ncsi.txt",  # Windows legacy
    "/redirect",  # Windows
    "/canonical.html",  # Firefox
    "/success.txt",  # Firefox
    "/check_network_status.txt",
}

PROBE_HOSTS = {
    "captive.apple.com",
    "www.apple.com",
    "connectivitycheck.gstatic.com",
    "connectivitycheck.android.com",
    "clients3.google.com",
    "clients1.google.com",
    "www.google.com",
    "www.msftconnecttest.com",
    "www.msftncsi.com",
    "detectportal.firefox.com",
    "nmcheck.gnome.org",
}


def host_only(host_header: str | None) -> str:
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.split(":")[0]


def should_redirect(path: str, host: str, own_hosts: set[str]) -> bool:
    """In AP mode: probe URLs and any foreign Host go to the setup page."""
    if path in PROBE_PATHS:
        return True
    if host in PROBE_HOSTS:
        return True
    return bool(host) and host not in own_hosts
