#!/usr/bin/env python3
"""Phase 0 button + LED test. Wire first:
    button: GPIO17 (pin 11) <-> GND (pin 9), internal pull-up
    LED:    GPIO18 (pin 12) -> resistor (220-330 ohm) -> LED anode; LED cathode -> GND (pin 14)

    python3 spikes/button_led_test.py [--button 17] [--led 18]

Press the button: each press/release prints with a timestamp and the gesture
the app would see. The LED ramps 0 -> 100 % to check PWM brightness, then
mirrors the button. Ctrl-C to stop.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from gpiozero import Button, PWMLED  # noqa: E402

from walloftext.hw.button import GestureDetector  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--button", type=int, default=17)
ap.add_argument("--led", type=int, default=18)
a = ap.parse_args()

led = PWMLED(a.led)
print("LED brightness ramp (watch for smooth steps)...")
for pct in (0, 5, 10, 25, 50, 75, 100):
    led.value = pct / 100
    print(f"  {pct:3d} %")
    time.sleep(0.7)
led.pulse(1, 1)
time.sleep(4)
led.off()

t0 = time.monotonic()
det = GestureDetector(lambda g: print(f"  -> gesture: {g}"),
                      lambda: (print("  -> 10 s reached: release now to reset"), led.blink(0.08, 0.08, n=3)))
btn = Button(a.button, pull_up=True, bounce_time=None)


def pressed():
    print(f"{time.monotonic() - t0:8.3f} pressed")
    led.value = 1
    det.press()


def released():
    print(f"{time.monotonic() - t0:8.3f} released")
    led.value = 0
    det.release()


btn.when_pressed = pressed
btn.when_released = released
print("Press the button: single, double, long (0.8 s), and a 10 s hold. Ctrl-C to stop.")
try:
    while True:
        det.poll()
        time.sleep(0.02)
except KeyboardInterrupt:
    pass
