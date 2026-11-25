#!/usr/bin/env bash
# Switch on SPI for WS2812 LED strips (Settings › Device › LED strip), then restart the Pi.
#
#   sudo bash deploy/enable_spi.sh          # strip 1 on GPIO10 (SPI0)
#   sudo bash deploy/enable_spi.sh --two    # also strip 2 on GPIO20 (SPI1)
#
# SPI0 is switched on without chip-select pins (spi0-0cs), so it only takes GPIO9-11.
# SPI1 also takes GPIO16 (its chip select), GPIO19 and GPIO21.
# The core clock is fixed at 500 MHz so the SPI timing the strips depend on can't drift.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
CFG=/boot/firmware/config.txt
[[ -f $CFG ]] || CFG=/boot/config.txt
cp "$CFG" "$CFG.bak-$(date +%Y%m%d%H%M%S)"

add() { grep -qxF "$1" "$CFG" || printf '%s\n' "$1" >> "$CFG"; }
# our lines go at the end, so make sure the last section there is [all] (not e.g. [pi5])
[[ "$(grep -E '^\[' "$CFG" | tail -n 1)" == "[all]" ]] || printf '\n[all]\n' >> "$CFG"
add "dtoverlay=spi0-0cs"
[[ "${1:-}" == "--two" ]] && add "dtoverlay=spi1-1cs,cs0_pin=16"
add "core_freq_min=500"

getent group spi >/dev/null && usermod -aG spi walloftext || true
echo "SPI is switched on in $CFG (a backup was saved next to it)."
echo "Restart the Pi to finish: sudo reboot"
