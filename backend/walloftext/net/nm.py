"""NetworkManager access. `NmcliClient` shells out to nmcli; `FakeNetworkManager`
simulates a radio, a router and phones for tests and the dev panel.

All methods are blocking; the Wi-Fi manager calls them through
`asyncio.to_thread`.
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Protocol

from ..config import AP_ADDRESS, AP_CON_NAME, CLIENT_CON_NAME, SETUP_SSID

log = logging.getLogger(__name__)

IFACE = "wlan0"


@dataclass
class Network:
    ssid: str
    signal: int
    security: str  # "open" | "wpa2" | "wpa3" | "wpa2/wpa3" | "enterprise" | "wep"
    band: str  # "2.4" | "5"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Link:
    ssid: str
    ip: str | None
    signal: int | None


@dataclass
class ActivateResult:
    ok: bool
    ip: str | None = None
    error: str | None = None  # "wrong_password" | "not_found" | "no_ip" | "failed"


class NetworkManagerClient(Protocol):
    def saved_client_profiles(self) -> list[str]: ...
    def scan(self) -> list[Network]: ...
    def ensure_ap_profile(self, psk: str) -> None: ...
    def set_ap_password(self, psk: str) -> None: ...
    def ap_up(self) -> bool: ...
    def ap_down(self) -> None: ...
    def ap_active(self) -> bool: ...
    def ap_clients(self) -> int: ...
    def add_client(self, ssid: str, password: str | None, hidden: bool, security: str | None) -> str: ...
    def activate(self, name: str, timeout_s: float) -> ActivateResult: ...
    def delete_profile(self, name: str) -> None: ...
    def client_link(self) -> Link | None: ...
    def all_ips(self) -> list[str]: ...


# ---------------------------------------------------------------- nmcli ----

def split_terse(line: str) -> list[str]:
    """Split one `nmcli -t` line on unescaped ':' and unescape '\\:' and '\\\\'."""
    out, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return out


def classify_security(flags: str) -> str:
    f = flags.upper()
    if not f.strip() or f.strip() == "--":
        return "open"
    if "802.1X" in f or "EAP" in f:
        return "enterprise"
    tokens = set(f.split())
    wpa3 = bool(tokens & {"WPA3", "SAE"})
    wpa2 = bool(tokens & {"WPA", "WPA1", "WPA2", "PSK"})
    if wpa3 and wpa2:
        return "wpa2/wpa3"
    if wpa3:
        return "wpa3"
    if "WEP" in f:
        return "wep"
    return "wpa2"


def classify_activation_error(text: str) -> str:
    t = text.lower()
    if "secrets were required" in t or "no secrets" in t or "802-1x supplicant" in t or "psk" in t and "invalid" in t:
        return "wrong_password"
    if "no network with ssid" in t or "not found" in t or "ssid-not-found" in t:
        return "not_found"
    if "ip configuration could not be reserved" in t or "dhcp" in t or "timeout" in t or "timed out" in t:
        return "no_ip"
    return "failed"


class NmcliClient:
    def __init__(self, nmcli: str = "nmcli"):
        self.nmcli = nmcli

    def _run(self, *args: str, timeout: float = 30, check: bool = True, secret: bool = False) -> str:
        cmd = [self.nmcli, *args]
        shown = " ".join(a if not secret else "***" for a in cmd[:6]) if secret else " ".join(cmd)
        log.debug("run %s", shown)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"nmcli failed ({p.returncode}): {p.stderr.strip() or p.stdout.strip()}")
        return p.stdout

    def saved_client_profiles(self) -> list[str]:
        out = self._run("-t", "-f", "NAME,TYPE", "con", "show")
        names = []
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) >= 2 and parts[1] == "802-11-wireless" and parts[0] != AP_CON_NAME:
                mode = self._run("-g", "802-11-wireless.mode", "con", "show", parts[0], check=False).strip()
                if mode in ("", "infrastructure"):
                    names.append(parts[0])
        return names

    def scan(self) -> list[Network]:
        self._run("dev", "wifi", "rescan", "ifname", IFACE, check=False, timeout=20)
        time.sleep(2)
        out = self._run("-t", "-f", "SSID,SIGNAL,SECURITY,FREQ", "dev", "wifi", "list", "ifname", IFACE)
        best: dict[str, Network] = {}
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) < 4 or not parts[0] or parts[0] == SETUP_SSID:
                continue
            ssid = parts[0]
            try:
                signal = int(parts[1])
            except ValueError:
                signal = 0
            freq = int(re.sub(r"\D", "", parts[3]) or 0)
            band = "5" if freq >= 4900 else "2.4"
            n = Network(ssid, signal, classify_security(parts[2]), band)
            if ssid not in best or best[ssid].signal < signal:
                best[ssid] = n
        return sorted(best.values(), key=lambda n: -n.signal)

    def ensure_ap_profile(self, psk: str) -> None:
        exists = self._run("-t", "-f", "NAME", "con", "show", check=False).splitlines()
        if AP_CON_NAME in exists:
            self.set_ap_password(psk)
            return
        self._run(
            "con", "add", "type", "wifi", "ifname", IFACE, "con-name", AP_CON_NAME,
            "autoconnect", "no", "ssid", SETUP_SSID,
            "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "802-11-wireless.channel", "6",
            "ipv4.method", "shared", "ipv4.addresses", f"{AP_ADDRESS}/24", "ipv6.method", "ignore",
            "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk,
            secret=True,
        )

    def set_ap_password(self, psk: str) -> None:
        self._run("con", "modify", AP_CON_NAME, "wifi-sec.psk", psk, secret=True)

    def ap_up(self) -> bool:
        p = subprocess.run([self.nmcli, "con", "up", AP_CON_NAME], capture_output=True, text=True, timeout=45)
        if p.returncode != 0:
            log.error("AP up failed: %s", p.stderr.strip())
        return p.returncode == 0

    def ap_down(self) -> None:
        self._run("con", "down", AP_CON_NAME, check=False)

    def ap_active(self) -> bool:
        out = self._run("-t", "-f", "NAME", "con", "show", "--active", check=False)
        return AP_CON_NAME in out.splitlines()

    def ap_clients(self) -> int:
        if not self.ap_active():  # in client mode station dump lists the router
            return 0
        try:
            p = subprocess.run(["iw", "dev", IFACE, "station", "dump"], capture_output=True, text=True, timeout=5)
        except FileNotFoundError:
            return 0
        return sum(1 for line in p.stdout.splitlines() if line.startswith("Station "))

    def add_client(self, ssid: str, password: str | None, hidden: bool, security: str | None) -> str:
        args = ["con", "add", "type", "wifi", "ifname", IFACE, "con-name", CLIENT_CON_NAME,
                "ssid", ssid, "autoconnect", "yes", "connection.autoconnect-priority", "10"]
        if hidden:
            args += ["802-11-wireless.hidden", "yes"]
        sec = (security or ("wpa2" if password else "open")).lower()
        if sec == "wpa3":
            args += ["wifi-sec.key-mgmt", "sae", "wifi-sec.psk", password or ""]
        elif sec == "wep":
            args += ["wifi-sec.key-mgmt", "none", "wifi-sec.wep-key0", password or ""]
        elif sec != "open" and password:
            args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
        self._run(*args, secret=True)
        return CLIENT_CON_NAME

    def activate(self, name: str, timeout_s: float) -> ActivateResult:
        try:
            p = subprocess.run(
                [self.nmcli, "--wait", str(int(timeout_s)), "con", "up", name],
                capture_output=True, text=True, timeout=timeout_s + 15,
            )
        except subprocess.TimeoutExpired:
            return ActivateResult(False, error="no_ip")
        if p.returncode != 0:
            return ActivateResult(False, error=classify_activation_error(p.stderr + p.stdout))
        link = self.client_link()
        if not link or not link.ip:
            return ActivateResult(False, error="no_ip")
        return ActivateResult(True, ip=link.ip)

    def delete_profile(self, name: str) -> None:
        self._run("con", "delete", name, check=False)

    def client_link(self) -> Link | None:
        out = self._run("-t", "-f", "GENERAL.CONNECTION,IP4.ADDRESS", "dev", "show", IFACE, check=False)
        con, ip = None, None
        for line in out.splitlines():
            key, _, val = line.partition(":")
            if key == "GENERAL.CONNECTION":
                con = val or None
            elif key.startswith("IP4.ADDRESS") and val and not ip:
                ip = val.split("/")[0]
        if not con or con == AP_CON_NAME:
            return None
        ssid = self._run("-g", "802-11-wireless.ssid", "con", "show", con, check=False).strip() or con
        signal = None
        wl = self._run("-t", "-f", "ACTIVE,SIGNAL", "dev", "wifi", "list", "ifname", IFACE, "--rescan", "no", check=False)
        for line in wl.splitlines():
            parts = split_terse(line)
            if parts and parts[0] == "yes":
                try:
                    signal = int(parts[1])
                except (ValueError, IndexError):
                    pass
        return Link(ssid=ssid, ip=ip, signal=signal)

    def all_ips(self) -> list[str]:
        p = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
        return [ip for ip in p.stdout.split() if ":" not in ip]


# ----------------------------------------------------------------- fake ----

@dataclass
class FakeNetworkManager:
    """In-memory radio. `networks` maps SSID → password (None for open).
    `router_up` False makes every client activation fail with not_found."""

    networks: dict[str, str | None] = field(default_factory=lambda: {"HomeWiFi": "correct-horse", "Neighbour": "x" * 8})
    router_up: bool = True
    profiles: dict[str, dict] = field(default_factory=dict)
    ap_psk: str | None = None
    ap_on: bool = False
    phones_on_ap: int = 0
    active_client: str | None = None
    calls: list[str] = field(default_factory=list)
    ip: str = "192.168.1.50"

    def __post_init__(self):
        self._lock = threading.Lock()

    def saved_client_profiles(self) -> list[str]:
        return list(self.profiles)

    def scan(self) -> list[Network]:
        self.calls.append("scan")
        if self.ap_on:
            return []  # one radio: scans while the AP is up are unreliable
        return [Network(s, 80 - i * 15, "open" if p is None else "wpa2", "2.4") for i, (s, p) in enumerate(self.networks.items())]

    def ensure_ap_profile(self, psk: str) -> None:
        if len(psk) < 8:
            raise RuntimeError("802-11-wireless-security.psk: property is invalid")
        self.ap_psk = psk

    def set_ap_password(self, psk: str) -> None:
        self.ensure_ap_profile(psk)
        self.calls.append("ap_password")

    def ap_up(self) -> bool:
        self.calls.append("ap_up")
        self.active_client = None
        self.ap_on = True
        return True

    def ap_down(self) -> None:
        self.calls.append("ap_down")
        self.ap_on = False
        self.phones_on_ap = 0

    def ap_active(self) -> bool:
        return self.ap_on

    def ap_clients(self) -> int:
        return self.phones_on_ap if self.ap_on else 0

    def add_client(self, ssid, password, hidden, security) -> str:
        self.calls.append(f"add:{ssid}")
        self.profiles[CLIENT_CON_NAME] = {"ssid": ssid, "password": password}
        return CLIENT_CON_NAME

    def activate(self, name: str, timeout_s: float) -> ActivateResult:
        self.calls.append(f"activate:{name}")
        prof = self.profiles.get(name)
        if not prof:
            return ActivateResult(False, error="failed")
        self.ap_on = False
        if not self.router_up or prof["ssid"] not in self.networks:
            return ActivateResult(False, error="not_found")
        if self.networks[prof["ssid"]] != prof["password"]:
            return ActivateResult(False, error="wrong_password")
        self.active_client = name
        return ActivateResult(True, ip=self.ip)

    def delete_profile(self, name: str) -> None:
        self.calls.append(f"delete:{name}")
        self.profiles.pop(name, None)
        if self.active_client == name:
            self.active_client = None

    def client_link(self) -> Link | None:
        if self.active_client and self.router_up and not self.ap_on:
            return Link(self.profiles[self.active_client]["ssid"], self.ip, 70)
        return None

    def all_ips(self) -> list[str]:
        if self.ap_on:
            return [AP_ADDRESS]
        return [self.ip] if self.client_link() else []

    # dev-panel helpers
    def simulate_boot_autoconnect(self) -> None:
        """NetworkManager autoconnects a saved profile at boot if the router is up."""
        for name, prof in self.profiles.items():
            if self.router_up and self.networks.get(prof["ssid"], object()) == prof["password"]:
                self.active_client = name
                return
