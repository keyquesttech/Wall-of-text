# Progress

## Phase 5: settings and connections
- Settings groups: Printer (darkness → ESC 7 heat, speed → band pause, extra feed, paper saver, paper
  estimate, test page), Fonts (upload .ttf/.otf, min readable size, default font/size), Button & light
  (gesture → action, fixed 10 s reset, brightness, pattern per event), Schedules (missed policy, quiet
  hours, daily limit, holiday mode, time zone), History retention, Display (reduce motion /
  transparency), Weather (place lookup, units), Calendars (secret iCal links, checked on add),
  Google Tasks (token upload + list picker, "Sign in again" when Google rejects it), Access
  (passwords, Ask for password, guest page, Waiting for your OK), Wi-Fi, Device (stats, heat and
  under-voltage banners, backup/restore, restart, shut down).
- Guest page `/note` (framework-free, open without sign-in when enabled): text + 8 built-in stickers,
  per-client rate limit, length cap, "wait for my OK" or "print straight away", quiet hours and the
  daily limit apply.
- Shared approval list `/api/inbox` (guest notes now, remote messages in Phase 6); the LED shows
  "message waiting".
- Backup zip (settings, schedules, templates, lists, fonts, allowed senders) with path-safe restore;
  never contains passwords, channel secrets or Google tokens (tested).
- `tools/google_auth.py`: PKCE installed-app flow on the PC, stdlib only, writes the token file.


## Phase 4: schedules, sources, routines
- Scheduler (`scheduler/engine.py`): local wall-clock times + zone (DST-safe), days of week, waits for
  NTP sync ("Waiting for the clock"), missed-run policy (late within 60 min / skip / always) with
  "Missed" History entries, quiet hours hold prints ("Held") under the same 60-minute rule, holiday
  mode, daily limit across Schedule/Guest/Remote, conditions (rain ≥, temp < / >, has events,
  has tasks) evaluated at run time; unavailable data never blocks a print.
- Sources: Open-Meteo weather with geocoding and a 3 h last-good cache, iCal calendars (recurrences,
  all-day, cancelled events dropped), Google Tasks via a token uploaded from the PC, bundled fortunes,
  countdowns. Failures print a plain line ("Calendar “Work” unavailable").
- Routines = schedules made of sections (date, weather, agenda, tasks, fortune, your own line,
  countdown, shopping list, divider). No time → a routine for the button / quick actions.
- UI: Schedules list with holiday mode, starters (Morning briefing, Umbrella alert, Daily fortune,
  Countdown, Shopping list, Custom), editor with time/days, section builder (reorder), conditions,
  preview and Print now. DESIGN REVIEW: built without the handoff's wizard mockups.


## Phase 3: queue, History, printer states, button, LED
- History screen: filters All / Manual / Schedules / Button / Guest / Remote, thumbnails, detail sheet
  with the printed bitmap, Print again, Try again for failed jobs (with a plain reason), remove, clear.
- Printer states in the UI: offline and out-of-paper banners on Create, status sheet with paper
  estimate, test page, "Out of paper" (user-reported until Phase 0 shows a readback) and "New roll".
- Button gestures run the mapped action (`actions.py`: reprint last, weather now, agenda today, random
  fortune, cancel queue, run routine); results come back to open apps as a toast over SSE.
  `/api/actions` exposes the same actions for the quick-action chips.
- LED controller driven by the status events: setup network > offline > paper out > printing >
  message waiting > idle, patterns and brightness from Settings.


## Phase 2: render and print path, shell, Create (Text)
- Renderer (`render/document.py`): blocks → 384-dot 1-bit bitmap; one function feeds both the preview
  and the printer. Block format in [DOCUMENT.md](DOCUMENT.md). Missing glyphs print as `□`,
  >50 % black warns, image styles photo (Floyd–Steinberg / Atkinson / ordered), sharp, halftone,
  `lighten` paper-safe limiter. Font registry with uploaded fonts and "min readable size".
- Persistent queue (`queue/worker.py`): single worker thread, `held → queued → printing → done | failed |
  cancelled`, progress over SSE, cancel between bands, crash → `failed (interrupted)` with Retry and no
  auto-reprint, offline/paper-out hold the queue, paper estimate from printed rows, retention pruning.
- API: `/api/preview`, `/api/print`, `/api/queue`, `/api/history`, `/api/printer/*`, `/api/fonts`, `/api/settings`.
- Frontend (Preact + TS + Vite, `frontend/`): shell with tab bar (side rail ≥768 px, third column ≥1200 px),
  status pill + sheet, Create › Text with live "As printed" preview, print-moment animation, Settings ›
  Wi-Fi and Access ported from Phase 1. Self-hosted fonts. Manifest and icons, no service worker.
- Golden tests: preview PNG == bitmap stored == bitmap the mock printer received.
- Playwright smoke test (`tools/smoke/`): sign-in, type, preview, print moment, status sheet, every tab
  at 390×844 and 1200×800, fails on any page error.
- Build: Node 22 lives in `~/.local/node` on this Pi for building only; the Pi serves static files.


## 20 Nov 2026: Phase 0 scripts and Phase 1 code (mock-tested)

The Pi has no electronics attached yet, and `design-handoff/` is still on the Windows PC.

### Phase 0
- Spike scripts written: `spikes/printer_probe.py`, `button_led_test.py`, `hotspot_test.sh`
  (safe to start over Wi-Fi SSH: it restores the home Wi-Fi by itself), `captive_probe_server.py`.
- Answers that need no hardware are in `spikes/SPIKE_RESULTS.md`. Three of them change the plan:
  1. **polkit rule needed** for nmcli as the service user (being in `netdev` is not enough on trixie).
  2. **Imager's Wi-Fi is a netplan profile** (`netplan-wlan0-*`, from cloud-init `network-config`).
     "Saved home Wi-Fi" means any infrastructure Wi-Fi profile. Reset and factory reset remove
     them all, including the cloud-init seed.
  3. The radio supports **AP + client on one channel**. v1 keeps one mode at a time, as planned.
- Printer, button, LED, phone captive sheets and `.local` resolution are still open (⏳).

### Phase 1 (code done, not yet installed on the Pi)
- Backend skeleton: config, SQLite (WAL, migrations), events/SSE, mock and real hardware layers
  (printer, button gestures incl. 10 s reset hold, LED patterns, system stats).
- Password file (`/etc/walloftext/passwords.txt`): defaults, recreated if missing, mtime reload,
  invalid values ignored with a warning, atomic writes, AP re-keyed on change.
- Sign-in: server-side sessions, HttpOnly + SameSite=Lax cookie, 30-day remember, lockout
  (5 tries → 60 s, doubling to 15 min), password change signs out other devices,
  "Ask for password" toggle, Host/Origin/Content-Type checks on mutating routes.
- Wi-Fi state machine (`SETUP_AP / CONNECTING / ONLINE / FALLBACK_AP`) with unit tests against a
  fake NetworkManager: router-slower-than-Pi, no retry while a phone is on the AP, 5-minute link
  loss, reset, a failed "Change network" returning to the old network, enterprise refusal.
- Captive portal: probe URLs and foreign hosts → `http://10.42.0.1/setup` in AP modes only;
  DNS catch-all and DHCP option 114 in `deploy/nm/wot-captive.conf`.
- `setup-ui/`: setup page (network list, password sheet, Other network, connecting, error banner),
  Sign in, Phase 1 settings placeholder (Device › Wi-Fi, Access passwords), dev panel.
  **Flag for design review** (BUILD_PLAN 5.6). The pages use their own CSS variables with
  fallbacks until `design-handoff/tokens.css` is in the repo.
- Setup slip (Wi-Fi QR, no readable password) and Connected slip, 384 px 1-bit.
- Deploy: `install.sh` (`--update`, `--keep-wifi`, refuses a factory-state install without
  Ethernet unless `--force`), systemd unit (port 80 via CAP_NET_BIND_SERVICE, hardened),
  polkit, udev (generic until the printer ID is known), journald cap, `walloftext-factory-reset
  [--shutdown]`, `walloftext-reset-password`, `deploy.ps1`.
- Tests: 45 passing (`cd backend && ../.venv/bin/python -m pytest -q`). Smoke-tested in mock mode:
  setup → connect → sign-in → settings, both slips printed.

### Installed on the Pi (`install.sh --keep-wifi`)
- `walloftext.service` active on port 80 as user `walloftext`, enabled at boot. It saw the existing
  Wi-Fi and went `connecting → online` in 0.1 s. `walloftext.local/` and the IP redirect to Sign in.
  A wrong password is refused, `root` signs in, and temperature/throttle read correctly. Printer shows
  `offline` (none attached).
- polkit rule confirmed: changing the setup Wi-Fi password from the site re-keys `wot-setup-ap`
  with no permission errors.
- Fixed: `iw station dump` in client mode lists the router, so `ap_clients()` now returns 0 unless
  the AP is up.

### Not done yet / next
- Phase 1 "done when" checks that need a phone or an Ethernet cable: factory state, phone joins
  `WallOfText-Setup`, captive page, power cycle with the router off.
- Phase 0 hardware answers (printer, button, LED, phones).
- Copy `design-handoff/` from the PC into the repo (needed for Phase 2 UI work).
- Clone handling (new SSH host keys and machine ID on first boot) is in Phase 9.
