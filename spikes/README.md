# Phase 0 spikes

Small throwaway scripts that answer the questions in BUILD_PLAN section 13 (Phase 0)
on the real Pi. Record every answer in [SPIKE_RESULTS.md](SPIKE_RESULTS.md).
Any "no" changes the plan before Phase 1 ships to the Pi.

All commands run **on the Pi**, from the repo folder (`~/Wall_of_text`).

## 1. Printer (needs the printer on USB and its own 5–9 V, 2 A+ supply)

```bash
sudo python3 spikes/printer_probe.py --only find
```
Note the `lsusb` line (vendor:product ID) and the device node.

```bash
sudo python3 spikes/printer_probe.py
```
Prints a text test, a raster sweep (band 24/48/64/128 rows, with and without pause),
two density tests, then tries four status queries. Report:
- did text and raster print correctly; which band/pause had no gaps or stalls and was fastest
- which density command visibly changed darkness (`ESC 7` or `DC2 #`)
- the four status replies with paper loaded, and again with **the lid open or no paper**

## 2. Button and LED (wire per the header of the script)

```bash
python3 spikes/button_led_test.py
```
Report: LED brightness steps visible and smooth? Single, double, long and the 30 s hold
all detected correctly? Which pins you used (the Power + Fan HAT may cover the header).

## 3. Hotspot and captive portal

Safe to start over Wi-Fi SSH: it backgrounds itself and puts your home Wi-Fi back
after 6 minutes. Your SSH session drops meanwhile.

```bash
sudo bash spikes/hotspot_test.sh --minutes 6
```
While `WallOfText-Setup` is up (about 30 s after starting):
1. iPhone: join `WallOfText-Setup`, password `rootroot`. Did a sign-in sheet open by itself
   showing "Spike captive page"?
2. Android: same.
3. Windows PC: join it, then `ssh <user>@10.42.0.1`. Did it work?

Afterwards, reconnect and send me:
```bash
cat spikes/hotspot_test.log spikes/captive_requests.log
```

## 4. `walloftext.local` on the home network

From each device, open `http://walloftext.local/` (after Phase 1 is installed) or run
`ping walloftext.local` (Windows PowerShell). Report Windows / iPhone / Android: resolves or not.
