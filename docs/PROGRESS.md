# Progress

## 24 Nov 2026 (night): fortunes, previews, paper, schedules, clock
- **Fortunes:** Settings › Fortunes uploads a CSV (or plain text, one per line), replace or add,
  download as CSV, built-in fortunes on/off. Picks are fair: each fortune prints once per round,
  and when a new round starts the ones from the last 7 days get 1/20 the weight.
- **Previews:** the blur was the browser shrinking the 1-bit bitmap with nearest-neighbour
  scaling (dropped dot columns: NOV → NCV), not the print font, so fonts are unchanged.
  `lib/crisp.ts` uses crisp scaling only at whole-pixel ratios and smooth scaling otherwise,
  and big previews open full size on tap (exact bitmap, 1 dot = 1 CSS px).
- **History:** keep 1 day to 1 year or forever, and up to 2000 prints or no limit.
- **Paper:** roll length setting (metres left shown) and a length calibration slip (two lines
  800 dot rows apart); the measured gap sets mm per row for the estimate only. Extra feed now counts.
- **Create:** List mode (shared shopping list) is back; quick chips stay when the printer is offline.
- **Schedules:** Create's Schedule button opens "Schedule this message" (once on a date, or
  repeating). New in Schedules opens the full editor, like "Start from Morning briefing", with
  "Start from" chips and Repeat / Once / No set time. One-off schedules switch off after running
  (DB migration 9, `once_on`). New missed-print option "Skip them and print a note": one slip
  saying how many were missed.
- **Date & time:** Settings › Date & time shows the Pi's clock, automatic (NTP) or set by hand
  ("Use this device's time"), and the time zone (also sets the system zone). A time set by hand
  counts as synced for the scheduler until the next reboot (no battery clock). polkit lets the
  service call systemd-timedated.

## 24 Nov 2026 (later): Google Calendar and Tasks through Google's APIs
- Google Tasks is back, and the calendar now uses the **Google Calendar API** instead of private
  iCal links. One sign-in covers both: Settings › Google (`docs/GOOGLE_SETUP.md`).
- Sign-in happens in the app from any phone or computer: paste the client ID and secret of your
  own Google Cloud "Desktop app" client once, tap Sign in with Google, then paste back the address
  the browser ends on (`http://127.0.0.1:53682/?code=…`). PKCE, state check, read-only scopes.
  Secrets go to `secrets.json` (0600), never in backups. `tools/google_auth.py` is no longer needed.
- Calendars and task lists to print are chosen in Settings › Google (default: main calendar,
  first list). Declined and cancelled events are left out; Meet links come from the API.
- Old iCal links are deleted from the stored settings at start. `icalendar` and
  `recurring-ical-events` are no longer dependencies. The wizard warns when Google isn't connected.

## 24 Nov 2026: Google Tasks removed
- Google Tasks is gone: the Tasks source, its token upload API and Settings page, the wizard's
  "Tasks" tile, the routine block, the "Only if any are due" condition, the To-do print template
  and `tools/google_auth.py`. The OAuth setup on the PC was too much hassle for what it gave.
- DB migration 8 strips Tasks blocks and conditions from saved schedules and switches off any
  schedule that printed only Tasks. Any old `google-token.json` in the data dir is deleted at start.
- The in-app shopping and to-do lists stay. Google Calendar (private iCal link) is unchanged.

## 21 Nov 2026 (later): fixes from use
- **Every print is rotated 180°** before it goes to the printer (Settings › Printer › "Rotate prints
  180°", on by default). Preview and History stay upright; only the paper is turned.
- **Fortune printing** failed on the Pi: a stale `backend/build` + `egg-info` in `/opt` made
  setuptools install an old file list without `sources/fortunes.json`. `install.sh` now deletes
  them before every install, force-reinstalls the package and fails loudly if the file is missing;
  `pyproject.toml` declares the data file; fortunes fall back to a short built-in list if unreadable.
- **"From" signature removed** from Create (side button, sheet and the printed "from …" line).
- **Wi-Fi reset hold is now 30 s** (was 10 s). A 10 s hold is an ordinary long press.
- **LED / progress for the whole print**: the printer buffers a slip in ~0.5 s, so jobs used to end
  (LED back to idle) while paper was still coming out. The driver now waits for the physical print
  (rows ÷ ~60 rows/s) and reports progress by time, so the LED pattern, status pill and progress
  bar last as long as the paper does.


## 21 Nov 2026: real printer + the handoff design
- **Printer (Gprinter CSN-A4, USB 0fe6:811e on /dev/usb/lp0)** tested with `spikes/printer_probe.py`
  (results in `spikes/SPIKE_RESULTS.md`). Changes: 128-row bands with no pause (a pause between
  bands left faint streaks; speed is motor-limited anyway), "Careful" speed = 48 rows + 20 ms,
  darkness via `ESC 7`, and **automatic paper-out detection** from `DLE EOT 4` (bits 0x60). Jobs
  wait while the lid is open or the roll is empty, resume when paper is back, and the roll estimate
  resets when paper returns after running out. A job cut short by paper running out shows
  "Paper ran out" with Retry.
- **Design**: `design-handoff/` is now in the repo and `tokens.css` is the app's base stylesheet
  (imported first by the frontend, served at `/tokens.css` for the setup, sign-in and guest pages).
  Screens rebuilt to the reference mockups: floating glass tab bar / side rail, status pill,
  Create (Edit | As printed, quick chips, 4-way mode switcher, paper strip you type on, side
  buttons Save / From / Clear, mode toolbars, Print + Schedule, in-canvas paper feed and tear,
  toast, History badge), Schedules (pink New, holiday card, Up next timeline, cards, empty state),
  the 4-step schedule wizard with the wheel time picker and day chips, the routine builder,
  History (search, Waiting cards, receipt grid, failed + Retry, shimmer), Settings (device card,
  icon rows, "‹ Settings" back button), guest page. Shopping list moved into a sheet from its
  quick chip.
- Text clarity fix confirmed on paper: thin strokes widened, pixel fonts on their grid; darkness 120
  (the default) reads well, so it stays.
- Two deliberate deviations for contrast (axe): the background blobs run at 18 % opacity
  instead of 36 %, and small muted text uses `#A3A8B0` instead of `--muted`. Both are noted in
  `frontend/src/styles.css`.


## Phase 8: layouts and hardening
- Layouts: phone (tab bar), ≥768 px side rail, ≥1024 px editor and live preview side by side,
  ≥1200 px third column with printer, queue progress, "Waiting for your OK" and recent prints.
- Reduce motion and reduce transparency (app setting and the system preference), skip link,
  focus-trapped sheets, labelled controls. axe-core across 26 screens (signed out and in):
  0 serious/critical issues (`tools/smoke/a11y.py`).
- systemd: `Type=notify` + `WatchdogSec=60`; the app pings only while the print worker is alive.
  Verified on this Pi: a frozen process was restarted by the watchdog within 60 s. `MemoryMax=400M`,
  no start-rate limit, journald capped at 64 MB.
- Security headers on every response (CSP, nosniff, frame-ancestors none, same-origin referrer).
- `install.sh` builds the frontend when `frontend/dist` is missing and Node is available.
- `tools/soak.py` for the 24-hour soak; power-cycle and watchdog procedures in
  [PI_TESTING.md](PI_TESTING.md). The 24 h soak and 20 power cycles need the printer and you.

## Status after Phase 8
All phases 0–8 have code, tests and docs. 132 backend tests, Playwright smoke test of every screen at
390×844 and 1200×800, axe accessibility check, all passing. Deployed to this Pi (mock-free, printer
offline because none is attached). Everything that needs real hardware, phones or accounts is
listed in [PI_TESTING.md](PI_TESTING.md). Phase 9 (master image) is optional and not started.
UI screens were built without `design-handoff/` (still on the PC) and need a design review.


## Phase 7: remaining Create modes and extras
- Draw: 384-dot canvas (1 px = 1 dot), pointer events for finger/mouse/pen, pen sizes, eraser,
  undo, three paper lengths, caption.
- Image: take a photo or choose one (`<input type=file capture>`), scaled on the phone before upload,
  Photo (smooth / crisp dither), Sharp, Halftone, brightness, contrast, invert, rotate, and the
  paper-safe "Lighten" offered automatically when the preview is over 50 % black.
- Templates: 8 built-in fill-ins (Note to self, Big message, To-do list, Wi-Fi for guests with QR,
  Greeting card, Recipe card, Chore chart, Sticker) with live preview, plus "Save as template" from
  Text mode.
- Shared shopping list (Create › List): add, tick, clear ticked, print; also a routine section and a
  button/quick action.
- Quick-action chips on Create run the same actions as the button.
- Paper saver (Phase 5 setting) trims gaps and trailing blank paper in the renderer, so the preview matches.


## Phase 6: remote messages
- One pipeline (`remote/pipeline.py`): dedupe by external id (persisted, so nothing prints twice
  after a reboot; marked before queueing) → allow-list (+ email SPF/DKIM alignment check) → per-sender
  rate limit → clean (HTML → text, quoted replies and signatures removed, blank lines collapsed, cap
  with "… (cut)") → approval ("Wait for my OK" goes to the shared list) → daily limit → quiet hours
  → print. Unknown senders are dropped and counted.
- Adapters: Email over IMAP with an app password (`imap-tools`), Telegram bot via long-polled
  `getUpdates` (offset committed after handling, photos, pairing mode, "Printed"/"Queued"
  replies), mock adapter reading `var/mock-inbox/*.json` + `POST /api/dev/inbound`. SMS not built.
- Channel manager with 60 s → 15 min back-off and "Can't connect" / "Sign in again" states.
- Secrets in `secrets.json` (0600), write-only over the API, excluded from backups (tested).
- UI: Settings › Connections › Remote messages (channel setup with step-by-step help, Telegram
  "Add me" pairing, allowed senders with approval mode, blocked count). History has the Remote filter.
- What to create and where to paste it: [REMOTE_SETUP.md](REMOTE_SETUP.md).
- Not yet tried against real Gmail / Telegram accounts (none configured on this Pi).


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
- 24 Nov 2026 · Print templates: print kit (render/kit), 14 weather icons, weather briefing, Weather now, To do, itinerary and every other slip on the design system; one end mark per printed copy; routines joined by cut rules; 37 golden images + preview/printer parity tests (tools/update_goldens.py).
