# Phase 0 spike results

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
| P1 | Printer `lsusb` vendor:product ID | ⏳ |
| P2 | Device node (`/dev/usb/lp0` or `/dev/ttyUSB0`) | ⏳ |
| P3 | Plain text prints | ⏳ |
| P4 | `GS v 0` raster prints a 384-px bitmap | ⏳ |
| P5 | Best band rows / pause with no stalls | ⏳ (code default: 24 rows, 50 ms) |
| P6 | Density command that works (`ESC 7` / `DC2 #`) | ⏳ |
| P7 | Paper-out / status readable over USB | ⏳ (if no: paper-out becomes user-reported) |
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
