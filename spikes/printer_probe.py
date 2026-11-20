#!/usr/bin/env python3
"""Phase 0 printer probe. Run on the Pi with the printer plugged in and powered:

    sudo python3 spikes/printer_probe.py              # everything below, in order
    sudo python3 spikes/printer_probe.py --only find  # just list USB devices / nodes

Answers for SPIKE_RESULTS.md:
  1. lsusb IDs and the device node (/dev/usb/lp0 or /dev/ttyUSB0)
  2. Does a plain text test print?
  3. Does GS v 0 raster print a 384-px bitmap? Which band size / pause is fastest without stalls?
  4. Which density/heat command has a visible effect?
  5. Does the printer answer status queries (paper-out) over USB?
"""
import argparse
import glob
import os
import select
import subprocess
import sys
import time

WIDTH = 384


def find():
    print("== lsusb")
    print(subprocess.run(["lsusb"], capture_output=True, text=True).stdout)
    nodes = sorted(glob.glob("/dev/usb/lp*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    print("== candidate device nodes:", nodes or "none")
    for n in nodes:
        print(subprocess.run(["udevadm", "info", "-q", "property", "-n", n], capture_output=True, text=True).stdout)
    return nodes


def open_node(node):
    if node.startswith("/dev/tty"):
        import termios
        fd = os.open(node, os.O_RDWR | os.O_NOCTTY)
        attrs = termios.tcgetattr(fd)
        attrs[4] = attrs[5] = termios.B19200  # Adafruit default baud; try 9600 if garbage
        attrs[3] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        return fd
    return os.open(node, os.O_RDWR)


def w(fd, data):
    os.write(fd, data)


def text_test(fd):
    print("== text test")
    w(fd, b"\x1b@")
    w(fd, b"Wall of Text spike\nPlain text line\n\x1bE\x01Bold line\x1bE\x00\n\n\n")


def bitmap(rows=200):
    """Checkerboard + gradient bars, 1 = black dot."""
    out = bytearray()
    for y in range(rows):
        for xb in range(WIDTH // 8):
            if y < 50:
                out.append(0xAA if (y // 2) % 2 == 0 else 0x55)
            elif y < 100:
                out.append(0xFF if xb < (WIDTH // 8) * (y - 50) / 50 else 0x00)
            else:
                out.append(0xFF if (xb // 6 + y // 25) % 2 == 0 else 0x00)
    return bytes(out)


def raster_test(fd, band_rows, pause):
    data = bitmap()
    wb = WIDTH // 8
    t0 = time.time()
    w(fd, b"\x1b@")
    w(fd, f"band={band_rows} pause={pause}\n".encode())
    for top in range(0, len(data) // wb, band_rows):
        rows = min(band_rows, len(data) // wb - top)
        w(fd, b"\x1dv0\x00" + bytes([wb, 0, rows & 0xFF, rows >> 8]) + data[top * wb:(top + rows) * wb])
        time.sleep(pause)
    w(fd, b"\n\n")
    print(f"   band={band_rows:3d} pause={pause:.3f}s sent in {time.time() - t0:.2f}s - check the paper for gaps/streaks")


def density_test(fd):
    print("== density: Adafruit 'ESC 7 n1 n2 n3' (heat dots, heat time, heat interval)")
    for heat_time in (60, 120, 200):
        w(fd, b"\x1b@" + b"\x1b7" + bytes([11, heat_time, 40]))
        w(fd, f"ESC 7 heat_time={heat_time}\n".encode())
        raster_test(fd, 24, 0.05)
    print("== density: 'DC2 # n' print density")
    for n in (0x00, 0x0F, 0x1F):
        w(fd, b"\x1b@" + b"\x12#" + bytes([n]))
        w(fd, f"DC2 # {n:#x}\n".encode())
        raster_test(fd, 24, 0.05)


def status_test(fd):
    print("== status queries (needs a readable node). Try once with paper, once with the lid open / no paper.")
    for name, cmd in [("DLE EOT 1 printer", b"\x10\x04\x01"), ("DLE EOT 4 paper", b"\x10\x04\x04"),
                      ("GS r 1 paper sensor", b"\x1dr\x01"), ("ESC v (Adafruit hasPaper)", b"\x1bv\x00")]:
        try:
            w(fd, cmd)
            r, _, _ = select.select([fd], [], [], 1.0)
            reply = os.read(fd, 16) if r else b""
        except OSError as exc:
            reply = f"error {exc}".encode()
        print(f"   {name:28s} -> {reply!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node")
    ap.add_argument("--only", choices=["find", "text", "raster", "density", "status"])
    a = ap.parse_args()
    nodes = find()
    if a.only == "find":
        return
    node = a.node or (nodes[0] if nodes else None)
    if not node:
        sys.exit("No printer node found. Is it powered (5-9 V, 2 A) and plugged in by USB?")
    print("== using", node)
    fd = open_node(node)
    try:
        if a.only in (None, "text"):
            text_test(fd)
        if a.only in (None, "raster"):
            print("== raster band/pause sweep")
            for band, pause in [(24, 0.05), (48, 0.05), (64, 0.05), (64, 0.0), (128, 0.0)]:
                raster_test(fd, band, pause)
        if a.only in (None, "density"):
            density_test(fd)
        if a.only in (None, "status"):
            status_test(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
