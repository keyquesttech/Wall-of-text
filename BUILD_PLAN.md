# Wall of Text: build plan and Claude Code handoff

Version 1.1 · 19 Nov 2026 · Companion to `design-handoff/HANDOFF.md` (UI spec). This file covers everything the UI spec does not: the Pi OS, first-boot Wi-Fi setup, the site password, the backend, hardware, scheduling, remote messages (email, Telegram, optional SMS), phases and risks.

**Read order for Claude Code:** `CLAUDE.md` → this file → `design-handoff/HANDOFF.md` (only the sections for the phase you are on).

**Rule of precedence:** where this file and `HANDOFF.md` disagree, this file wins. Section 3 lists every override. Never edit anything under `design-handoff/`.

---

## 1. Decisions at a glance

| Topic | Decision |
|---|---|
| OS | Raspberry Pi OS Lite (64-bit), Debian 13 "Trixie". NetworkManager is the network stack |
| Flashing tool | Raspberry Pi Imager 2.x on Windows |
| Hostname | `walloftext` → `http://walloftext.local/` (avahi/mDNS, plain HTTP, port 80) |
| Starting point | The SD card already holds Raspberry Pi OS and the app, in "factory state" (section 2). The user flow never assumes a fresh Pi OS install |
| Setup network | Pi hosts Wi-Fi `WallOfText-Setup` (WPA2) whenever it has no working home Wi-Fi. Password comes from the password file, default `rootroot` (WPA2 needs 8 or more characters, so `root` is impossible) |
| Backend | Python 3.13 + FastAPI + uvicorn, one systemd service, SQLite |
| Rendering | Pillow, on the Pi. One function makes both the paper bitmap and the "As printed" preview |
| Printer I/O | Raw ESC/POS-style bytes to the USB printer node (`/dev/usb/lp0`), behind a driver interface |
| Frontend | Preact + TypeScript + Vite, built to static files the Pi serves. No Node on the Pi |
| Hardware access | `gpiozero` (lgpio backend) for the arcade button and LED |
| Dev loop | Develop on Windows against a mock printer, mock GPIO and mock network manager; deploy to the Pi over SSH |
| Weather | Open-Meteo (free, no key), behind a provider interface |
| Calendar | Private iCal URL (no OAuth) |
| Google Tasks | OAuth token created once on the PC and uploaded to the Pi (section 9) |
| Site password | One plain-text file on the Pi, default `root`, changeable in the GUI or by editing the file (section 10) |
| Remote messages | Email (IMAP) and Telegram bot in v1, both free; real SMS optional and paid (section 9.2) |

## 2. The SD card: what "first boot" assumes

The setup procedure in section 5 assumes the card **already holds Raspberry Pi OS and the Wall of Text app, in factory state**. Whoever uses it installs nothing: they power it on, join `WallOfText-Setup`, and pick their Wi-Fi.

**Factory state means:** hostname `walloftext`, the service enabled at boot, the setup-network profile created, **no home Wi-Fi saved**, the password file at its defaults (section 10), empty history and schedules. `install.sh` ends by leaving the machine in this state, and `sudo walloftext-factory-reset` returns to it at any time (`--shutdown` powers off afterwards, ready for imaging).

**Building the card (once, by you):**

1. Raspberry Pi Imager 2.x on Windows. Device: Raspberry Pi 4. OS: Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**, the Debian 13 "Trixie" release. Storage: a high-endurance microSD (see imaging below for size).
2. Imager customisation: hostname `walloftext`; your own username and password (this is the Linux login and SSH password, separate from the site password in section 10); SSH on, with your public key if you have one; time zone `Europe/London`, keyboard `gb`; Wi-Fi country `GB` (Pi OS can keep the radio blocked until a country is set, so check `rfkill list`); **home Wi-Fi left blank**.
3. Boot the Pi with an **Ethernet** cable to your router. Run `ssh <user>@walloftext.local`, then `deploy/install.sh` (Phase 1).
4. `sudo walloftext-factory-reset --shutdown`. The card is now in factory state.

**More cards, or a backup:** image the finished card and flash that image onto others. Make the master image from the smallest card that fits (16 GB) so the image stays small. Cards cloned from one image share SSH host keys and the machine ID, so regenerate both on the first boot of each clone (Claude Code to implement and test). Two devices with the same hostname on one network become `walloftext.local` and `walloftext-2.local`.

**Working on a card in factory state:** with no Ethernet and no home Wi-Fi saved, join `WallOfText-Setup` from your PC and run `ssh <user>@10.42.0.1`.

Raspberry Pi OS Lite is the base because it has no desktop, runs 64-bit on the Pi 4, and uses NetworkManager by default, which the hotspot approach in section 5 depends on.

## 3. Overrides to `HANDOFF.md`

| # | HANDOFF.md says | Change |
|---|---|---|
| 1 | Address is `printer.local` (8 places: `HANDOFF.md` ×3, `Settings.dc.html` ×3, `Guest.dc.html`, `State-NoPi.dc.html`) | Use **`walloftext.local`** everywhere (`walloftext.local/note` for guests). Put the hostname and product name in one config constant. The product name is still an open question; "Wall Printer" strings come from the same constant so a rename is one line |
| 2 | Fonts load from Google Fonts in every mockup (Inter, VT323, Silkscreen, Space Mono) | **Self-host all fonts** as `woff2` in `frontend/public/fonts/`. The Pi often has no internet (and has none in setup mode). The same font files feed the server-side renderer, so screen and paper use identical glyphs |
| 3 | Installable PWA with a service worker that caches the shell (section 11) | **Not possible over `http://walloftext.local`.** Service workers need a secure context (HTTPS or localhost). v1 ships the manifest, icons, `apple-touch-icon` and `apple-mobile-web-app-capable` meta tags, but **no service worker**. iOS "Add to Home Screen" should still open it standalone (verify on the real iPhone). Android Chrome will only offer a shortcut, not a true install. The "Can't reach Wall Printer" screen (State-NoPi) is shown only when the app is already open and loses the Pi (SSE drop plus failed polls). If the Pi is off when you launch, the browser's own error page appears. HTTPS with a local CA is a later option, not v1 |
| 4 | Image mode: "take or pick a photo" | Use `<input type="file" accept="image/*" capture>`, not `getUserMedia` (also needs a secure context) |
| 5 | Settings › Device shows "fan quiet" and the too-hot banner says "Fan is at full speed" | The Power + Fan HAT fan runs whenever power is present; there is no software fan control or fan state. Show **temperature and throttle state** only. Remove the fan wording (design change needed, small) |
| 6 | Paper level "About 60% left" | The printer almost certainly has no roll-diameter sensor. Estimate it from printed rows (section 6.5). Paper-out detection depends on the Phase 0 spike |
| 7 | No Wi-Fi setup or reset screens | Add them (section 5.6). Build from existing components; flag for design review |
| 8 | Button: single, double, long press are all user-mappable | Reserve **hold 10 s = Wi-Fi reset** (not mappable). Keep the three mappable gestures as designed |
| 9 | Nothing on missed schedules, clock, outages | Section 7 defines the policy |
| 10 | Settings › Device "software updates" | v1 shows the version only. Updates ship through `deploy/deploy.ps1` from the PC. No in-app updater in v1 |
| 11 | Connections: Google Calendar and Google Tasks with "Sign in again" | Calendar uses a private iCal URL (no sign-in). Only Tasks uses Google OAuth. See section 9 |
| 12 | "No sign-up, no login; at most an optional 4-digit PIN" (section 1) and Settings › Access "Require a PIN" | Password-protected by default. One site password (default `root`) lives in a text file on the Pi and can be changed in Settings › Access or by editing the file. Needs a new **Sign in** screen. The 4-digit PIN is dropped (section 10) |
| 13 | History filters: All, Manual, Schedules, Button, Guest. Connections lists only Google and Weather | Add a **Remote** filter. Add Settings › Connections › **Remote messages** (Email, Telegram, optional SMS) with allowed senders. Guest notes and remote messages share the "Waiting for your OK" list (section 9.2) |

## 4. Architecture

```
Phone / laptop browser ──HTTP :80──►  walloftext.service  (FastAPI, user "walloftext")
                                       ├─ api/        REST + SSE (/api/events)
                                       ├─ render/     blocks → 1-bit 384-px bitmap (+ preview PNG)
                                       ├─ queue/      single worker, SQLite-backed jobs
                                       ├─ scheduler/  schedules, routines, conditions
                                       ├─ sources/    weather, iCal, Google Tasks, quotes
                                       ├─ remote/     inbound adapters (email, Telegram, SMS) + approval pipeline
                                       ├─ auth/       password file, sessions, login rate limit
                                       ├─ printer/    driver interface: escpos_usb | mock
                                       ├─ hw/         button, LED, system stats (real | mock)
                                       ├─ net/        Wi-Fi state machine, nmcli wrapper, captive-portal routes
                                       └─ store/      SQLite (WAL) + migrations
NetworkManager ── hotspot profile (setup AP) + client profile (home Wi-Fi)
avahi-daemon   ── walloftext.local
USB printer    ── /dev/usb/lp0
GPIO           ── arcade button, panel LED
```

Repo layout to create inside `Wall_of_text/`:

```
backend/            pyproject.toml, walloftext/ (modules above), tests/
frontend/           Vite app, src/, public/fonts/
setup-ui/           tiny framework-free page for Wi-Fi setup (loads inside phone captive-portal sheets)
tools/              google_auth.py (section 9), dev scripts
spikes/             Phase 0 scripts, SPIKE_RESULTS.md
deploy/             install.sh, deploy.ps1, systemd/, nm/, udev/
```

Hardware abstraction: `WOT_HW=real|mock` selects implementations of `Printer`, `Button`, `Led`, `SystemInfo` and `NetworkManagerClient`. The mock printer writes the PNG it would print plus the raw bytes to `backend/var/mock-printer/`. The mock network manager lets a dev panel simulate each state in section 5. The mock button is a dev endpoint that fires `single|double|long|reset`.

Python dependencies (keep the list short): `fastapi`, `uvicorn[standard]`, `pydantic`, `pillow`, `numpy`, `segno` or `qrcode`, `apscheduler`, `httpx`, `icalendar`, `recurring-ical-events`, `sse-starlette`, `python-multipart`, `imap-tools`, and a `pi` extra with `gpiozero` and `lgpio`. Telegram and Twilio are called with plain `httpx`, no vendor SDKs. The site password is plain text in a file by design (section 10); session tokens are random and held server-side.

## 5. First boot and Wi-Fi setup (the core of this phase)

Assumes the card is in factory state (section 2).

### 5.1 States

```
BOOT ─ no saved home Wi-Fi ─────────────────────────► SETUP_AP   (stays until set up)
BOOT ─ saved home Wi-Fi ─► CONNECTING (up to 120 s) ─► ONLINE
                                         └─ timeout ─► FALLBACK_AP ─(home Wi-Fi seen again)─► ONLINE
ONLINE ─ link lost for 5 min ─► CONNECTING
any state ─ reset (web or 10 s button hold) ─► SETUP_AP (home Wi-Fi forgotten)
```

Why `FALLBACK_AP` exists and why the hotspot profile must have `autoconnect no`: after a power cut the Pi boots faster than the router. If NetworkManager auto-started the hotspot, the Pi would sit in setup mode forever. The app (not NetworkManager) decides when to raise the AP. In `FALLBACK_AP`, retry the saved network every 60 s, but only when **no phone is connected to the AP** (check `iw dev wlan0 station dump`), because a single radio cannot be an AP and a client at the same moment reliably. Verify that behaviour in Phase 0.

Ethernet never counts as "provisioned". With a cable plugged in, the site is reachable on Ethernet too, but the Wi-Fi state machine ignores it. This keeps development simple and makes the first-boot flow testable.

### 5.2 Hotspot profile (NetworkManager)

Created by `install.sh` and kept in step with the `setup_wifi_password` line of the password file (section 10):

```bash
nmcli con add type wifi ifname wlan0 con-name wot-setup-ap autoconnect no ssid WallOfText-Setup \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "<setup_wifi_password>"
```

Bring up with `nmcli con up wot-setup-ap`, down with `nmcli con down wot-setup-ap`. 2.4 GHz for the widest phone compatibility. NetworkManager's `shared` mode runs its own dnsmasq for DHCP and DNS on the AP.

**The setup Wi-Fi password cannot be `root`.** WPA2 passphrases must be 8 to 63 characters, so the default is `rootroot`. Phase 0 confirms NetworkManager rejects anything shorter. Whenever the password changes (in the GUI or by editing the file) the app runs `nmcli con modify wot-setup-ap wifi-sec.psk <new>`, and the new password applies the next time the AP comes up.

The app creates the home-Wi-Fi profile itself, named `wot-client`, and never stores the password: NetworkManager keeps it (root-only). Run nmcli as the `walloftext` user via membership of the `netdev` group, or a narrow polkit rule. If that does not work in Phase 0, fall back to a sudoers whitelist for the exact nmcli commands.

### 5.3 Captive portal

Goal: joining `WallOfText-Setup` opens the setup page automatically.

1. **DNS catch-all.** Create `/etc/NetworkManager/dnsmasq-shared.d/wot-captive.conf` with `address=/#/10.42.0.1`. Every name resolves to the Pi while the AP is up. (Verify in Phase 0 that NetworkManager's dnsmasq honours that directory.)
2. **HTTP probes.** Phones and PCs test connectivity with fixed URLs. In AP mode, answer these with `302` to `http://10.42.0.1/setup` instead of the "all good" reply they expect:
   - Apple: `/hotspot-detect.html` (host `captive.apple.com`)
   - Android: `/generate_204` (hosts `connectivitycheck.gstatic.com`, `clients3.google.com`)
   - Windows: `/connecttest.txt` and `/ncsi.txt` (hosts `www.msftconnecttest.com`, `www.msftncsi.com`)
   - Firefox: `/canonical.html` (host `detectportal.firefox.com`)
   - Anything else on an unknown Host in AP mode also redirects to `/setup`.
3. **Redirect to the IP, not the `.local` name**, inside the captive sheet. Phone captive sheets can be unreliable with mDNS names. The `.local` name remains the address people use once the Pi is on the home network.
4. Optional extra: DHCP option 114 (captive-portal API URL) so newer phones show the sheet more reliably.
5. The setup page is `setup-ui/`, a small static page with **no framework, no CDN, no `backdrop-filter` dependency**, sharing `tokens.css` variables. Captive sheets are restrictive browsers.

In normal (online) mode none of this is active: no DNS catch-all, no probe redirects.

### 5.4 Setup flow

1. Phone joins `WallOfText-Setup`. Easiest route: scan the Wi-Fi QR printed on the **setup slip** (format `WIFI:T:WPA;S:WallOfText-Setup;P:<setup_wifi_password>;;`). Otherwise type the setup Wi-Fi password (default `rootroot`). The slip prints the network name, address and QR, but not the password as readable text.
2. Captive sheet opens `/setup`. If it does not, the slip also says "open http://walloftext.local or http://10.42.0.1".
3. Page lists nearby networks (name, signal, lock icon), plus "Other network…" for hidden SSIDs. The list comes from a scan taken **just before the AP was raised** and cached (`GET /api/wifi/scan`); rescanning while the AP is up is unreliable on one radio.
4. User picks a network, enters the password, taps Connect. Page says plainly what happens next: "Your phone will leave WallOfText-Setup. Join your home Wi-Fi, then open walloftext.local. If the Pi can't connect, WallOfText-Setup comes back within a minute."
5. Server replies `202`, waits about 4 seconds so the reply is delivered, then: creates `wot-client`, brings the AP down, activates `wot-client`, waits up to 30 s for an IP address.
   - **Success:** state `ONLINE`, avahi announces `walloftext.local` on the new network, the printer prints a confirmation slip ("Connected to <SSID>. Open http://walloftext.local. IP 192.168.x.x").
   - **Failure:** delete `wot-client`, raise the AP again, store `last_error` (wrong password / network not found / no IP). When the phone rejoins the AP, `/setup` shows the error banner and the form again.
6. The user reconnects the phone to the home Wi-Fi and opens `http://walloftext.local/`.

This is the same pattern as balena's wifi-connect (NetworkManager plus captive portal). Read its source for edge cases, but build it in-app so the UI is yours and there is only one web server.

### 5.5 Reset

- **Website:** Settings › Device › Wi-Fi › "Forget this network and start setup again". A confirmation sheet explains the Pi will disappear from the home network until set up again. A signed-in session is required (section 10). API: `POST /api/wifi/reset`.
- **Button:** hold the arcade button for 10 s at any time. The LED does a fast triple blink at 10 s; releasing then triggers the reset. Works even when the site is unreachable.
- **CLI:** `sudo walloftext-factory-reset` (installed by `install.sh`).
- All three: delete `wot-client*` profiles, raise the AP, print a setup slip if the printer is ready. The password file is not touched.

### 5.6 New screens needed (not in the design handoff)

Build from existing components (`.glass`, `.lrow`, `.banner`, `.btn-green`, `.sheet`) and mark for design review:

1. **Setup welcome and network list** (`/setup`, AP mode only).
2. **Password sheet** with show/hide and an "Other network" form.
3. **Connecting** state (spinner, the sentence in 5.4 step 4) and **Failed** state (pink banner plus icon plus plain sentence).
4. **Settings › Device › Wi-Fi** detail: current network, signal, IP, address, "Change network" and "Forget and start setup again".

### 5.7 Edge cases to handle and test

| Case | Behaviour |
|---|---|
| Router slower than the Pi after a power cut | `CONNECTING` waits 120 s, then `FALLBACK_AP` retries every 60 s when no AP client is present |
| Router replaced or password changed | Same path as above; the AP reappears by itself; user redoes setup |
| Hidden SSID | Supported via "Other network…" |
| Open or WPA3 or 5 GHz-only network | Pi 4 supports 2.4 and 5 GHz; list shows both; pass the security type through to NetworkManager |
| WPA-Enterprise, or a network with its own captive login | Not supported in v1; show a plain sentence saying so |
| `.local` does not resolve on a phone | Android's resolver gained `.local` support in a Nov 2021 update, so older phones may fail. Always show the IP in Settings › Device and on the setup slip |
| No internet in AP mode | Nothing may depend on a CDN. The clock is not synced (section 7) |
| Wi-Fi password in logs | Never log request bodies for `/api/wifi/*` |
| AP mode is open to anyone who joins | The AP is WPA2 and its password comes from the password file (default `rootroot`; change it). `/api/wifi/*` setup endpoints need no sign-in only while `mode` is `setup_ap` or `fallback_ap`, because joining the AP already proves the password |

## 6. Printing

### 6.1 Document and renderer

The document is the block list in `HANDOFF.md` section 12. The renderer lays blocks out top to bottom on a 384-px-wide canvas and converts to mode `1`. 384 dots over 48 mm is 8 dots per mm. The preview endpoint returns exactly the bitmap that would be sent (golden-image tests prove the preview equals the print path).

- Fonts: bundled TTF/OTF, rendered with anti-aliasing **off** for crisp bitmap output. Sizes S/M/L/XL are 18/22/30/40 px (`HANDOFF.md` section 4).
- Image styles: Photo dither (Floyd–Steinberg, optionally Atkinson), Sharp (threshold), Halftone (ordered or dot screen).
- Paper-safe limiter: Adafruit's guide for this printer says dense images can stick and stall, large solid areas streak, and photos work best under about 50% dot density. Warn above roughly 50% black coverage, and offer to lighten.
- "Min readable size" for uploaded fonts: render a test string at each size, measure stroke width, and report the smallest size that keeps strokes at least 2 dots wide.

### 6.2 Printer driver

Interface: `Printer.print_bitmap(img_1bit, copies, extra_feed, on_progress)`, `Printer.test_page()`, `Printer.status()`. Implementations: `escpos_usb` and `mock`.

- Device node: current Tiny printers appear as `/dev/usb/lp0` (older units can appear as `/dev/ttyUSB0`). Add a udev rule matching the printer's vendor and product ID (recorded in Phase 0) that gives group access and a stable symlink `/dev/walloftext-printer`. Add the service user to the `lp` group.
- Send the bitmap in bands (start around 24 to 64 rows) with a short pause between bands. Phase 0 tunes band size and pause for speed versus stalls.
- Try `python-escpos` (`escpos.printer.File`) first. Adafruit's guide for this printer does not document its command set, so it may not accept every ESC/POS command. If the spike shows odd behaviour, replace the library with a small hand-written raster writer.
- Print darkness and speed (Settings › Printer) map to the printer's heat or density setting and the inter-band pause. Adafruit's library exposes a heat/density value (default 120) that can be lowered to avoid jams. Confirm the exact commands in Phase 0.

### 6.3 Queue worker

- One consumer, persistent in SQLite. States: `queued → printing → done | failed | cancelled`.
- Progress in 0–100 pushed over SSE (`/api/events`), with 3 s polling as the fallback.
- Cancel works on queued jobs, and on the active job between bands (then feed and stop).
- After a crash, a job left in `printing` becomes `failed (interrupted)` with a Retry button. Never reprint it automatically (avoids duplicate slips).
- Failure causes: device node missing or write error → `offline`; paper out (if detectable) → `paper_out`. Jobs wait in the queue in both states, as designed.
- Manual prints are never blocked by quiet hours or the daily limit. Scheduled, guest and remote prints are.

### 6.4 History

Store the document JSON and the 1-bit PNG (a few KB each). Retention: last 200 prints or 30 days, whichever is fewer, configurable. SQLite in WAL mode with `synchronous=NORMAL` to limit SD-card wear. Source labels: Manual, Schedule, Button, Guest, Remote.

### 6.5 Paper estimate

Rows printed × (1 mm / 8 rows) ÷ roll length. The Tiny printer takes 10 m rolls, so a roll is about 80,000 rows including feeds. `paperPercent = 100 − rowsSinceNewRoll / 800`. "I loaded a new roll" resets the counter. This is an estimate and the UI must say "About".

## 7. Clock, schedules and outages

The Pi 4 has **no real-time clock** and the Power + Fan HAT does not add one. After a power cut the clock is wrong until NTP syncs, which needs the home network.

- The scheduler does not run until `timedatectl show -p NTPSynchronized` is `yes`. Until then Create works but Schedules shows a pink banner "Waiting for the clock".
- **Missed-run policy (default):** if a schedule's time passed while the Pi was off or unsynced, print it late if within 60 minutes, otherwise skip it and log a "Missed" entry in History. Setting: Settings › Schedules › "If the printer was off".
- **Quiet hours (default):** a scheduled print due in quiet hours is held and printed when quiet hours end (marked "Held" in the queue), subject to the same 60-minute rule.
- Time zone comes from Settings › Schedules, default `Europe/London`. Store times as local wall-clock plus zone and handle DST.
- Conditions ("Only print if…") are evaluated at run time, using the freshest data. If a source is unreachable, print what is available with a plain line such as "Weather unavailable", never fail silently. Cache the last good weather for up to 3 hours.
- Holiday mode pauses every schedule. Daily print limit counts scheduled, guest and remote prints only.

## 8. Hardware

- **Pins are config, not code.** Defaults: button on GPIO17 (pin 11) to GND with the internal pull-up, LED on GPIO18 (pin 12, hardware PWM) through a resistor. The Power + Fan HAT stacks on the header, so confirm which pins are reachable (riser header or wires) before wiring.
- **Button gestures:** 50 ms debounce; single press after a 300 ms double-press window; double press; long press at 800 ms; reserved 10 s hold for Wi-Fi reset. Actions are the same functions the quick-action chips use: reprint last, weather now, agenda today, random fortune, cancel queue, run routine `<id>`.
- **LED:** single colour, brightness 0–100%, patterns Off, Solid, Slow pulse, Blink, per event (Idle, Printing, New message waiting, Paper out, Error). Driven from the same status events as the UI.
- **System stats:** temperature from `/sys/class/thermal/thermal_zone0/temp`, throttle flags from `vcgencmd get_throttled`, uptime, free disk. No fan state (override 5).
- **Restart and Shut down:** `systemctl reboot` and `systemctl poweroff` through a narrow polkit rule or sudoers entry for the service user.
- **Power note (for the enclosure, not code):** the printer cannot run from USB power and needs 5 to 9 V at 2 A or more, never above 9 V (Adafruit). The Pi Hut Power + Fan HAT takes 7 to 16 V. A single supply in the 7 to 9 V window, for example 8 V, satisfies both. Budget roughly 5 A: printer at least 2 A plus the Pi at up to about 2 A at that voltage (estimate).

## 9. Connections and remote messages

### 9.1 Data sources

| Source | v1 approach |
|---|---|
| Weather | Open-Meteo. Settings stores a place name; geocode once, store lat/lon. Behind a `WeatherProvider` interface |
| Calendar | Google Calendar "Secret address in iCal format" (read-only link) per calendar, parsed with `icalendar` + `recurring-ical-events`. Any other `.ics` URL works too. No OAuth |
| Google Tasks | Needs OAuth. **Google's limited-input device flow cannot be used**: it only supports the `email/openid/profile`, Drive `appdata/file` and YouTube scopes, not Calendar or Tasks. Default: `tools/google_auth.py` runs the normal installed-app flow on your Windows PC (loopback redirect works there), saves a token file, and Settings › Connections › Tasks accepts the upload (or `scp`). Set the Google Cloud consent screen to **In production**: in Testing status Google expires refresh tokens after 7 days. It stays unverified, which is fine for personal use |
| Quotes and fortunes | Bundled local JSON (offline). Users can add their own |
| Countdown | Computed locally |
| Remote messages | Email, Telegram, optional SMS: see 9.2 |
| Home Assistant, Webhook | "Coming later" in the design; not in v1 |

If Tasks OAuth turns out to be more hassle than it is worth, the fallback is a local to-do and shopping list inside the app (the design already has a shared shopping list).

### 9.2 Remote messages: text or email something and it prints

Goal: send a message from your phone, from anywhere, and it prints on the wall. Nothing is exposed to the internet. The Pi only makes **outbound** connections and polls, so there is no port forwarding and no public URL. It needs the home Wi-Fi to have internet, so nothing arrives while the Pi is in setup mode.

| Channel | How it reaches the Pi | Cost and catches | v1? |
|---|---|---|---|
| **Email** | A dedicated mailbox the Pi checks over IMAP every 60 s. You email that address from anywhere, with any mail app | Free. Use a **personal Gmail account with an app password**. Google removed "less secure apps" password access on 30 Sep 2024, and Google Workspace accounts now need OAuth, so do not use a Workspace address. Any provider that still allows IMAP with an app password also works | Yes |
| **Telegram** | A bot you create with @BotFather. The Pi long-polls Telegram's `getUpdates`, which works behind a home router with no public URL. You message the bot from the Telegram app | Free. It is a chat message, not an SMS | Yes |
| **SMS (real text message)** | Needs a number that can receive texts. Option A: a Twilio UK number, polled through its REST API (no webhook needed). New UK numbers need an approved regulatory (KYC) bundle first, then a monthly number fee plus per-message fees. Option B: a SIM modem or HAT with a SIM card, read over serial or USB (extra hardware and a SIM plan, no cloud account) | Paid | Optional, last in Phase 6 |

A plain SMS to an ordinary phone number can only reach the Pi through a paid number or a SIM. The free route to text-message behaviour is the Telegram bot. The free route that needs nothing installed on the sender's phone is email.

**One pipeline, small adapters:**

- Each channel is an adapter with `poll() → [InboundMessage]`, where `InboundMessage = { channel, sender_id, sender_name, subject?, body, attachments?, received_at, external_id }`. `external_id` (IMAP UID plus Message-ID, Telegram update ID, Twilio message SID) is stored so a message is **never printed twice**, even after a reboot.
- Pipeline: allow-list check → rate limit → clean → approval (if required) → quiet hours → render → queue.
- **Allowed senders** (Settings › Connections › Remote messages): each has a display name and one or more identifiers (email address, Telegram numeric user ID, phone number). Anyone else is **dropped and counted** ("3 blocked this week"), never printed.
- Email spoofing: also require the mailbox provider's `Authentication-Results` header to show `spf=pass` or `dkim=pass` for the From domain; otherwise treat the sender as unknown. Telegram user IDs cannot be spoofed. SMS sender numbers can be, so SMS defaults to "Wait for my OK".
- **Approval** per sender: "Print straight away" (default) or "Wait for my OK". Pending items appear in the same "Waiting for your OK" list as guest notes (Settings › Access). History source label **Remote**, with its own filter chip.
- **Print format:** a white-on-black line "from <name> · via Email · 18:42", then the text. Email: subject in bold, body as plain text (strip HTML, signatures and quoted replies, collapse blank lines). Default cap 600 characters or 40 lines, ending "… (cut)", adjustable in settings. Emoji and glyphs the print font lacks are replaced by a small placeholder box so the paper never has silent gaps.
- **Images (stretch goal in the same phase):** Telegram photos and email image attachments go through the Image pipeline (Photo dither), size-capped, with the paper-safe limiter on.
- **Limits:** per-sender rate limit (default 10 per hour) and the daily cap shared with guest and scheduled prints. Quiet hours hold messages until they end. If the printer is offline or out of paper, messages wait in the queue as normal.
- **Acknowledgements:** the Telegram bot replies "Printed" or "Queued: the printer is out of paper". Email and SMS send no reply by default (SMS replies cost money, email replies need SMTP). A setting can enable them.
- **Secrets** (IMAP app password, Telegram bot token, Twilio auth token) go in `/var/lib/walloftext/secrets.json` (mode `0600`). Never in the password file, never in backups, never in logs.
- **Failures:** a failed poll (no internet, bad credentials) shows the channel as "Can't connect" with a plain sentence in Settings › Connections, with back-off from 60 s up to 15 min. Rejected credentials show the pink "Sign in again" style chip.
- **Setup help shown in the UI.** Email: make a new Gmail account, turn on 2-Step Verification, create an app password, enter the address and app password. Telegram: message @BotFather, send `/newbot`, paste the token, then press "Add me" and message the new bot once. Pairing mode lasts 5 minutes and captures your user ID from that first message, which you then confirm.
- **Dev:** mock adapters read JSON files from `backend/var/mock-inbox/` so the whole pipeline is testable with no accounts. `POST /api/dev/inbound` does the same.

## 10. Access: password, sign-in and guest notes

### 10.1 The password file

One plain-text file owned by the service user (mode `0600`): `/etc/walloftext/passwords.txt`.

```
# Wall of Text passwords. Plain text on purpose: edit this file, or use Settings > Access.
# Changes apply straight away. No restart needed.
gui_password=root
setup_wifi_password=rootroot
```

- `gui_password` protects the website and everything behind it. Default `root`. 4 to 64 characters.
- `setup_wifi_password` is the password of the `WallOfText-Setup` network. Default `rootroot`, because WPA2 needs 8 to 63 characters and `root` is too short. Same file, separate line.
- `install.sh` creates the file with these defaults. **If the file is missing, the app recreates it with the defaults.** Deleting it, or running `sudo walloftext-reset-password`, is the recovery path if you forget a password.
- The app checks the file's modification time on each sign-in request and applies changes at once: every session is signed out, and a new `setup_wifi_password` is pushed into the `wot-setup-ap` profile. A bad value (blank, too short, unreadable line) is ignored, the previous valid value stays in force, a pink banner appears in Settings › Access ("The setup Wi-Fi password in the file is too short, so the old one is still in use") and a line is logged.
- Changing a password in the GUI writes the file atomically (temp file plus rename, same owner and mode).
- "Reset Wi-Fi" (section 5.5) never touches this file. The file is excluded from backups.
- **Know the trade-offs:** it is stored in plain text by design, so anyone with the SD card or a shell on the Pi can read it, and it is typed over plain HTTP on your home network (no HTTPS in v1). Treat it as a household lock, not strong security. Say so in the Access help text. Both defaults are guessable, so Settings › Access shows a pink banner ("You're still using the default password") until each has been changed.
- Scope: this password protects the website and the setup network only. The Linux login and SSH password is the one you set in Imager and is separate.

### 10.2 Sign-in

- The whole site and API require sign-in by default (Settings › Access › "Ask for password", default on). Open without sign-in: the Sign in page, static assets, `/note` and its POST (when enabled), the captive-portal and `/api/wifi/*` setup routes in AP modes only, and a minimal `/api/health`.
- New screen: **Sign in**. Password field, "Remember this device for 30 days" (on by default), plain error sentence. It lives in `setup-ui/` so signed-out visitors never download the app bundle. Build from existing components; flag for design review.
- Session cookie: random token held server-side, `HttpOnly`, `SameSite=Lax` (`Secure` is impossible on plain HTTP), 30 days. Compare passwords with `hmac.compare_digest`. After 5 wrong attempts from one client, lock out for 60 s, doubling up to 15 min. A password change signs out every other device.
- Settings › Access (replaces the 4-digit PIN row): **Password** (current, new, confirm), **Setup Wi-Fi password** (8 to 63 characters; saying plainly that it re-keys the setup network), and the "Ask for password" toggle.
- Reject cross-site requests: require `Content-Type: application/json` on mutating routes and check `Origin` and `Host` against `walloftext.local`, the device IPs and (in AP mode only) the AP address.

### 10.3 Guest page and the shared approval list

- Guest page `/note`: when enabled, no sign-in. Rate limit (for example 5 notes per 10 minutes per client), length cap, stickers and text only in v1. Mode from Settings › Access: print straight away or wait for approval.
- Guest notes and remote messages (9.2) share one list, **Waiting for your OK**, with Decline and Print it. API: `GET /api/inbox`, `POST /api/inbox/:id/approve`, `POST /api/inbox/:id/decline`. This supersedes the guest-only approve endpoint in `HANDOFF.md` section 12.
- Open question from the design: should the button approve waiting items? Default: no. The LED shows "New message waiting" and approval happens in the app.

## 11. API additions (on top of `HANDOFF.md` section 12)

| Endpoint | Purpose |
|---|---|
| `GET /api/wifi/status` | `{ mode: "setup_ap"\|"connecting"\|"online"\|"fallback_ap", ssid, ip, hostname, signal, last_error, ap: { ssid, clients } }` |
| `GET /api/wifi/scan` | Cached networks `[ { ssid, signal, security, band } ]` |
| `POST /api/wifi/connect` | `{ ssid, password?, hidden?, security? }` → `202` |
| `POST /api/wifi/reset` | `{ confirm: true }`; signed-in session required |
| `POST /api/print/setup-slip` | Prints the address, IP, Wi-Fi QR and the setup network name |
| `POST /api/device/restart` · `/shutdown` | Power controls |
| `GET /api/device` | Version, temperature, throttle flags, uptime, disk, hostname, IPs, clock-synced flag |
| `GET/POST /api/backup` | Zip of settings, schedules, templates and uploaded fonts. Excludes the password file, channel secrets and Google tokens |
| `GET /api/auth/status` | `{ signed_in, ask_for_password, default_password_in_use, default_setup_wifi_password_in_use, password_file_warning? }` |
| `POST /api/auth/login` · `/logout` | `{ password, remember }` → session cookie |
| `POST /api/auth/password` | `{ current, new }`: changes `gui_password` in the file |
| `POST /api/auth/setup-wifi-password` | `{ current_password, new }` (8 to 63 characters): changes `setup_wifi_password` and re-keys the AP profile |
| `GET/PATCH /api/remote/channels/:id` | Channel state, enable or disable, write-only credentials |
| `POST /api/remote/channels/:id/test` · `POST /api/remote/pairing/start` | Connection test; start Telegram pairing mode |
| `GET/POST/PATCH/DELETE /api/remote/senders` | Allowed senders and their approval mode |
| `GET /api/inbox` · `POST /api/inbox/:id/approve` · `/decline` | Shared approval list for guest notes and remote messages |
| Probe routes | The captive-portal URLs in section 5.3, active only in AP modes |
| Dev only (mock hardware) | `POST /api/dev/button`, `POST /api/dev/net-state`, `POST /api/dev/inbound` |

## 12. Frontend plan

- Preact + TypeScript + Vite, `wouter` or `preact-iso` for routes, signals for state. Lift `tokens.css` as the base stylesheet. Use its variables, no hard-coded hexes.
- `setup-ui/` is separate from the SPA bundle so the captive sheet loads a tiny page. The Sign in page lives there too, so signed-out visitors never download the app.
- SSE hook with a 3 s polling fallback. API client typed from the backend's OpenAPI schema.
- Motion per `HANDOFF.md` section 9 with `.rm` and `.solid` handling. Sounds are optional assets, off by default.
- Tests: Vitest for logic; Playwright smoke tests at 390 × 844 and 1200 × 800 against the mock backend.
- Dev: `vite dev` proxies `/api` to a mock backend on the PC or to the real Pi.

## 13. Phases

Each phase ends with something runnable and a short note in `docs/PROGRESS.md`.

**Phase 0: Spikes on the real Pi (no app code).** Scripts in `spikes/`, results in `spikes/SPIKE_RESULTS.md`.
- Printer: record `lsusb` IDs and the device node. Print a 384-px bitmap and a test page. Find which raster and density commands work. Find out whether the printer reports paper-out or status over USB. Tune band size and pause.
- Button and LED: confirm pins; PWM brightness works.
- Hotspot: create the AP with the nmcli commands above using password `rootroot`, and confirm NetworkManager refuses `root`. Confirm a phone gets an address and that `ssh <user>@10.42.0.1` works over the AP. Add the DNS catch-all and a tiny HTTP server that redirects the probe URLs. Test iPhone and Android. Test that the AP can be dropped and a client connection made, and that the AP can be raised again.
- `walloftext.local` resolves from the Windows PC, an iPhone and an Android phone, on the home network.
- Done when SPIKE_RESULTS.md answers every question above. **Any "no" changes the plan before Phase 1.**

**Phase 1: Skeleton, provisioning, sign-in, deploy.**
- Backend skeleton, config, SQLite, mock and real hardware layers, systemd unit (`AmbientCapabilities=CAP_NET_BIND_SERVICE` to bind port 80), `install.sh` (ends in factory state), `deploy.ps1`, `walloftext-factory-reset [--shutdown]`, `walloftext-reset-password`.
- Password file, sign-in page, session middleware, login rate limit, default-password flags.
- Wi-Fi state machine with unit tests against a fake NetworkManager; `setup-ui/`; captive routes; setup slip; reset by site, button and CLI.
- Done when, from a card in factory state (section 2): it hosts `WallOfText-Setup` (password `rootroot`); a phone joins and gets the setup page; the Pi joins the home Wi-Fi; `http://walloftext.local/` shows the Sign in page; `root` signs in and a wrong password is refused; editing `gui_password` in the file takes effect with no restart; changing `setup_wifi_password` re-keys the setup network; Reset returns to setup; and a power cycle with the router off then on rejoins by itself within about two minutes.

**Phase 2: Render and print path, shell, Create (Text).**
- Renderer, `/api/preview`, `/api/print`, queue worker, frontend shell (tokens, background, tab bar and side rail, status pill and sheet), Create in Text mode, "As printed", the full print-moment animation.
- Done when the preview PNG and the paper match for a set of golden documents.

**Phase 3: Queue, History, printer states, button, LED.**
- History with retention, failed jobs and Retry, paper-out and offline states, status SSE, button gestures and actions, LED patterns.

**Phase 4: Schedules.**
- Scheduler, missed-run and quiet-hours policy, sources, conditions, routines, list, wizard, routine builder, holiday mode.

**Phase 5: Settings and connections.**
- All settings groups, font manager and upload, weather and iCal connections, Tasks OAuth path, Access (change password, change setup Wi-Fi password, "Ask for password", default-password banners, guest page and the shared approval list), Device (stats, backup and restore, restart, shut down).

**Phase 6: Remote messages.**
- Adapter interface, pipeline, allowed senders, approval, dedupe, secrets file, Settings › Connections › Remote messages, History "Remote" filter. Email (IMAP) first, then Telegram, then the optional image support, then optional SMS (Twilio polling) if you decide to pay for a number.
- Done when: from an allowed email address and an allowed Telegram account a message prints within about 90 seconds; an unknown sender is dropped and counted; a message is never printed twice, including after a reboot; "Wait for my OK" works from the shared list; quiet hours hold messages and release them at the end; and a Telegram acknowledgement arrives.

**Phase 7: Remaining Create modes and extras.**
- Draw, Image, Templates, quick-action chips, shared shopping list, paper saver.

**Phase 8: Layouts and hardening.**
- Tablet and desktop layouts, reduce motion and transparency, accessibility pass, `systemd` watchdog, journald limits, 24-hour soak test with scheduled prints, 20 power-cycle test.

**Phase 9 (optional): master image.** Build the master image described in section 2 (factory state, regenerated SSH keys and machine ID on first boot of each clone) and test it on a second card.

## 14. Assumptions and open decisions

Change any of these before or during the phase that needs them.

| # | Item | Default used |
|---|---|---|
| 1 | Product name | Keep "Wall Printer" in UI strings via one constant; hostname and setup SSID say `walloftext` |
| 2 | Setup Wi-Fi password | `rootroot`, because WPA2 needs 8 to 63 characters and `root` is impossible. Editable in the password file or the GUI |
| 3 | Site password | `root`, protection on by default, plain-text file, device remembered for 30 days |
| 4 | Scope of "the password" | Protects the website and the setup network only. The Linux and SSH password is the one set in Imager |
| 5 | Fan | No software fan state; temperature and throttle only |
| 6 | Google Tasks | OAuth token made on the PC (section 9); drop Tasks if it proves awkward |
| 7 | Missed schedules | Print late within 60 minutes, else skip and log |
| 8 | Quiet hours | Hold scheduled, guest and remote prints and release them when quiet hours end |
| 9 | PWA | Plain HTTP, no service worker (override 3) |
| 10 | Button approves waiting items | No |
| 11 | Light mode | Not built in v1 |
| 12 | LED colour | Single colour, as designed |
| 13 | Remote channels | Email and Telegram in v1. SMS is optional and paid |
| 14 | Unknown senders | Dropped and counted, never printed |
| 15 | Setup slip | Network name, address and Wi-Fi QR; no readable password |

## 15. Risks, in order of how much they could change the plan

1. **Printer protocol and status.** The "Tiny" printer may not return paper-out or status over USB, which drives the paper-out and offline states. Phase 0 settles it. If there is no readback, paper-out becomes user-reported and offline means the device node is gone.
2. **Captive portal reliability on real phones.** Phase 0 settles it. Fallback is the printed setup slip with the address and Wi-Fi QR.
3. **One radio for both AP and client.** Handled by the state machine and clear on-screen wording. A cheap USB Wi-Fi adapter is a hardware fix if it proves flaky.
4. **`.local` on older Android.** IP fallback everywhere.
5. **Printer and Pi power budget** (section 8).
6. **Remote message providers change the rules.** Gmail app passwords, Telegram's API and Twilio's UK number rules can all change. Each adapter is isolated, so one breaking does not stop the others. SMS has a running cost and a sign-up hurdle.
7. **Guessable defaults.** `root` and `rootroot` are easy to guess. The setup network only exists during setup or fallback and needs someone within Wi-Fi range, and the banners nudge you to change both. Anyone on your home Wi-Fi who knows `root` can use the site.

## 16. Start prompts for Claude Code

Paste the one for the phase you are starting. Each assumes Claude Code has read `CLAUDE.md`, this file and the relevant parts of `design-handoff/HANDOFF.md`.

**Phase 0:**
> Read BUILD_PLAN.md sections 2, 5, 6.2 and 8. Write the Phase 0 spike scripts in `spikes/` (printer probe, button and LED test, hotspot and captive-portal test using the setup password `rootroot`) with a README telling me exactly what to run on the Pi and what to report back. Do not write app code yet. Record results in `spikes/SPIKE_RESULTS.md` as I report them.

**Phase 1:**
> Read BUILD_PLAN.md in full and `spikes/SPIKE_RESULTS.md`. Implement Phase 1. Create the repo layout from section 4, the mock and real hardware layers, the password file and sign-in (section 10), the Wi-Fi state machine with unit tests against a fake NetworkManager, `setup-ui/` including the Sign in page, the captive routes, the setup slip, reset by site, button and CLI, `install.sh` (which must end in the factory state from section 2), `walloftext-factory-reset`, `walloftext-reset-password`, `deploy.ps1` and the systemd unit. Develop against `WOT_HW=mock` on Windows. Stop when the Phase 1 "done when" list can be checked on the Pi, and give me the exact commands to run.

**Phase 6:**
> Read BUILD_PLAN.md sections 9.2, 10.3 and 13 (Phase 6). Implement remote messages with mock adapters first so every rule in the plan has a test (allow-list, spoof check, dedupe across restarts, approval, quiet hours, rate limits, print format). Then the real Email (IMAP) adapter, then Telegram. Do not implement SMS unless I say I have a number or modem. Tell me exactly what accounts and tokens I need to create and where to paste them.

**Any other phase:**
> Implement Phase N from BUILD_PLAN.md section 13, using the matching sections of design-handoff/HANDOFF.md as the UI spec. Keep the overrides in BUILD_PLAN.md section 3. Use mock hardware for development, add the tests the plan lists, and finish by updating `docs/PROGRESS.md` and listing anything I need to try on the Pi.
