"""Which GPIO pins each device uses, and the checks that stop two devices sharing one.

Pin numbers are BCM GPIO numbers (what gpiozero and `pinout` call GPIO17, not header pin 11).
"""
from __future__ import annotations

USABLE = range(2, 28)  # GPIO2-27 on the 40-pin header
# Pins with a fixed job on this build; using them for something else breaks that job.
RESERVED = {
    2: "I2C (used by HATs)",
    3: "I2C (used by HATs)",
    14: "the serial console",
    15: "the serial console",
}
# WS2812 strips are driven from an SPI data line (the app doesn't run as root, which the
# PWM/PCM methods need). Each SPI bus also takes its clock and input pins.
STRIP_PINS = {
    10: {"bus": 0, "label": "GPIO10 (SPI0 MOSI, header pin 19)", "claims": (9, 10, 11)},
    20: {"bus": 1, "label": "GPIO20 (SPI1 MOSI, header pin 38)", "claims": (16, 19, 20, 21)},
}
PWM_HW = (12, 13, 18, 19)  # hardware-PWM capable; any pin works for the fan (software PWM)


def claims(cfg: dict) -> dict[int, str]:
    """GPIO → the device using it, for every enabled device in the settings."""
    used: dict[int, str] = {}

    def take(pin, who):
        if pin is not None:
            used.setdefault(int(pin), who)

    if cfg.get("button", {}).get("enabled", True):
        take(cfg["button"].get("pin", 17), "the button")
    if cfg.get("led", {}).get("enabled", True):
        take(cfg["led"].get("pin", 18), "the panel light")
    fan = cfg.get("fan", {})
    if fan.get("enabled"):
        take(fan.get("pin", 12), "the fan")
    neo = cfg.get("neopixel", {})
    if neo.get("enabled"):
        for i, s in enumerate(neo.get("strips") or []):
            info = STRIP_PINS.get(int(s.get("pin", 10)))
            for p in (info["claims"] if info else (s.get("pin"),)):
                take(p, f"LED strip {i + 1}")
    return used


def problems(cfg: dict) -> dict[str, str]:
    """Device → a sentence, for pins that clash or can't be used."""
    out: dict[str, str] = {}
    seen: dict[int, str] = {}

    def check(device: str, pins: tuple[int, ...], who: str):
        for p in pins:
            if p not in USABLE:
                out[device] = f"GPIO{p} isn't on the header. Use GPIO2 to GPIO27."
                return
            if p in RESERVED:
                out[device] = f"GPIO{p} is kept for {RESERVED[p]}. Pick another pin."
                return
            if p in seen and seen[p] != who:
                out[device] = f"GPIO{p} is already used by {seen[p]}."
                return
        for p in pins:
            seen[p] = who

    if cfg.get("button", {}).get("enabled", True):
        check("button", (int(cfg["button"].get("pin", 17)),), "the button")
    if cfg.get("led", {}).get("enabled", True):
        check("led", (int(cfg["led"].get("pin", 18)),), "the panel light")
    fan = cfg.get("fan", {})
    if fan.get("enabled"):
        check("fan", (int(fan.get("pin", 12)),), "the fan")
    neo = cfg.get("neopixel", {})
    if neo.get("enabled"):
        buses = set()
        for i, s in enumerate(neo.get("strips") or []):
            pin = int(s.get("pin", 10))
            info = STRIP_PINS.get(pin)
            if not info:
                out[f"strip{i}"] = f"LED strips work on {' or '.join(v['label'] for v in STRIP_PINS.values())}."
                continue
            if info["bus"] in buses:
                out[f"strip{i}"] = "Two strips can't share one data pin. Chain them, or use the other pin."
                continue
            buses.add(info["bus"])
            check(f"strip{i}", info["claims"], f"LED strip {i + 1}")
    return out
