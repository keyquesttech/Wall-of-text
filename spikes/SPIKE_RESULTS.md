# Phase 0 spike results

Printer tested 21 Nov 2026 (USB, Gprinter CSN-A4).

Status key: ✅ answered · ⏳ needs hardware or a phone · ⚠️ answered, changes the plan

Pi: Raspberry Pi 4, Raspberry Pi OS Lite 64-bit (Debian 13 trixie), kernel 6.18.50+rpt-rpi-v8,
NetworkManager 1.52.1, Python 3.13.5. Checked 20 Nov 2026 with no electronics attached.

## Already answered (no hardware needed)

| Question | Answer |
|---|---|
| NetworkManager is the network stack | ✅ Yes, NM 1.52.1 manages `wlan0` and `eth0` |
| Does NM's shared-mode dnsmasq read `/etc/NetworkManager/dnsmasq-shared.d`? | ✅ Yes: the NM binary passes `--conf-dir=/etc/NetworkManager/dnsmasq-shared.d` |
| Can the radio be an AP at all? | ✅ `iw list` supports `AP` mode |
| AP and client at the same time? | ✅ ⚠️ `iw` reports `#{ managed } <= 1, #{ AP } <= 1 … #channels <= 1`, so a concurrent AP and client are possible on the **same channel** (needs a second virtual interface). v1 keeps the plan's one-mode-at-a-time design; this is a possible later improvement for `FALLBACK_AP` |
| Can the service user run nmcli without sudo? | ⚠️ Not by default. As a `netdev` member `nmcli general permissions` shows `network-control` and `settings.modify.system` as `auth`. **Plan change:** `install.sh` installs a polkit rule (`deploy/polkit/50-walloftext.rules`) that allows the `walloftext` user NetworkManager actions plus reboot and power-off |
| Where does the Imager home Wi-Fi live? | ⚠️ cloud-init `network-config` on `/boot/firmware` → netplan → NM profile `netplan-wlan0-<SSID>`. **Plan change:** "saved home Wi-Fi" means any infrastructure Wi-Fi profile, not only `wot-client`. A successful setup deletes the others. Reset deletes all of them, and factory reset also strips `wifis:` from netplan and `/boot/firmware/network-config` so cloud-init cannot restore it on a cloned card |
| Does `nmcli --offline` reject a 4-character WPA2 key? | ✅ No, offline mode writes it anyway. The live daemon check is in `hotspot_test.sh`. The app validates 8 to 63 characters itself, so this cannot bite |
| Clock | ✅ `timedatectl` reports `NTPSynchronized=yes`, time zone `Europe/London` |
| Temperature and throttle readable | ✅ `/sys/class/thermal/thermal_zone0/temp` = 44.3 °C, `vcgencmd get_throttled` = `0x0` (user needs `video` group) |
| Python deps on Pi | ✅ `python3-gpiozero` 2.0.1 and `python3-lgpio` 0.2.2 from apt; venv uses `--system-site-packages` |

## Waiting for hardware / phones

| # | Question | Answer |
|---|---|---|
| P1 | Printer `lsusb` vendor:product ID | ✅ `0fe6:811e`, reports as "Gprinter CSN-A4" ("ICS Advent Parallel Adapter" in lsusb's table), bidirectional usblp |
| P2 | Device node (`/dev/usb/lp0` or `/dev/ttyUSB0`) | ✅ `/dev/usb/lp0`, group `lp`; the udev rule's `/dev/walloftext-printer` symlink appears |
| P3 | Plain text prints | ✅ |
| P4 | `GS v 0` raster prints a 384-px bitmap | ✅ test page from the app printed correctly |
| P5 | Best band rows / pause with no stalls | ⚠️ A 50 ms pause between bands leaves faint streaks (24/48/64-row bands); no pause (64 or 128 rows) is clean. The motor limits speed to ~62 dot rows/s (~7.8 mm/s) whatever the band size. **Now: 128-row bands, no pause** ("Careful" speed: 48 rows, 20 ms) |
| P6 | Density command that works (`ESC 7` / `DC2 #`) | ✅ Both visibly change darkness. Darkness slider uses `ESC 7` heat time |
| P7 | Paper-out / status readable over USB | ✅ `DLE EOT 4`: `0x12` with paper, `0x72` lid open (bits `0x60` = paper end). `GS r 1`: `0x60` → `0x6C`. `ESC v`: `0x00` → `0x04`. **Paper-out is now detected automatically**; paper back after running out resets the roll estimate |
| P8 | Text clarity | ⚠️ "Unclear on some letters": thin fonts at small sizes draw 1-dot strokes (Space Mono S/M, Inter S) and VT323/Silkscreen are uneven off their pixel grid. **Now:** fonts with >8 % 1-dot strokes at a size are widened by one dot; VT323 prints at 24/30/40/48 and Silkscreen at 16/24/32/40 for S/M/L/XL |
| B1 | Pins reachable with the Power + Fan HAT | ⏳ (defaults GPIO17 button, GPIO18 LED) |
| B2 | PWM brightness smooth | ⏳ |
| B3 | Gestures detected correctly | ⏳ |
| H1 | NM refuses WPA2 key `root` | ⏳ `hotspot_test.sh` |
| H2 | Phone gets an address on the AP | ⏳ |
| H3 | `ssh <user>@10.42.0.1` over the AP | ⏳ |
| H4 | DNS catch-all answers every name with 10.42.0.1 | ⏳ |
| H5 | iPhone captive sheet opens and shows the page | ⏳ |
| H6 | Android captive sheet opens and shows the page | ⏳ |
| H7 | AP down → client up → AP up again works | ⏳ |
| M1 | `walloftext.local` from Windows | ⏳ |
| M2 | `walloftext.local` from iPhone | ⏳ |
| M3 | `walloftext.local` from Android | ⏳ |
