# Wall of Text: project context

Written 23 Nov 2026 as a hand-over: what exists, how it fits together, what was decided and why,
and what is still open. For the full plan read `BUILD_PLAN.md`; for the UI spec `design-handoff/HANDOFF.md`;
for a dated log `docs/PROGRESS.md`.

## 1. Where everything is

| What | Where |
|---|---|
| Code | GitHub `keyquesttech/Wall-of-text`, branch `main`. Working copy on the Pi at `~/Wall_of_text` |
| Running app | `http://walloftext.local/` (or the Pi's IP, currently `192.168.86.250`), port 80 |
| Installed copy | `/opt/walloftext` (code + `venv`), service `walloftext.service` (user `walloftext`) |
| Data | `/var/lib/walloftext` (SQLite `walloftext.db`, uploaded fonts, `secrets.json`, Google token) |
| Passwords | `/etc/walloftext/passwords.txt`: site `root`, setup Wi-Fi `rootroot` (defaults, still in use) |
| Linux login | user `pi` (SSH). The Pi pushes to GitHub with a deploy key (`~/.ssh/walloftext_deploy`, host alias `github-walloftext`) |
| Node (build only) | `~/.local/node` on the Pi (Node 22). The Pi serves the built `frontend/dist`; Node is not used at run time |

## 2. Hardware (as tested)

- Raspberry Pi 4, Raspberry Pi OS Lite 64-bit (Debian 13 trixie), NetworkManager 1.52, Python 3.13.
- **Printer: Gprinter CSN-A4**, USB `0fe6:811e`, `/dev/usb/lp0` (udev adds `/dev/walloftext-printer`), 384 dots wide.
  - `GS v 0` raster works. A pause between bands leaves faint streaks, so bands go back to back
    (128 rows; "Careful" speed = 48 rows + 20 ms). Motor speed ~60 dot rows/s.
  - Darkness: `ESC 7` heat time (also `DC2 #` works). Default 120 reads well (confirmed on paper).
  - **Paper-out is detected**: `DLE EOT 4` returns `0x12` with paper, `0x72` with the lid open (bits `0x60`).
  - The printer buffers a whole slip; the driver waits for the real print time so the LED,
    status pill and progress bar last as long as the paper moves.
  - **Every print is rotated 180°** before sending (Settings › Printer › "Rotate prints 180°", on).
- Button (GPIO17) and LED (GPIO18, PWM): code done, **not yet wired or tested**.
- Wi-Fi setup network (`WallOfText-Setup`) and captive portal: code done, **not yet tried with a phone**.

## 3. Architecture in one screen

- **Backend** `backend/walloftext/` (FastAPI, one process): `api/` routes, `auth/` (password file,
  sessions, lockout), `net/` (Wi-Fi state machine over nmcli, captive portal), `render/` (one renderer
  for preview and paper), `queue/` (persistent print queue + worker thread), `printer/` (USB ESC/POS
  driver + mock), `scheduler/`, `sources/` (Open-Meteo weather, Google Calendar and Tasks APIs, fortunes),
  `remote/` (email IMAP, Telegram, approval inbox), `hw/` (button gestures, LED controller, stats),
  `templates_lists.py`, `actions.py` (quick actions shared by button and chips), `watchdog.py`.
- **Frontend** `frontend/` (Preact + TypeScript + Vite). Base stylesheet is
  `design-handoff/tokens.css`; `src/styles.css` is a thin app layer on top.
- **Framework-free pages** `setup-ui/`: Wi-Fi setup (captive portal), Sign in, guest note page `/note`.
- **Deploy** `deploy/`: `install.sh` (full / `--update` / `--keep-wifi`), systemd unit (Type=notify,
  60 s watchdog), polkit rule (nmcli + reboot for the service user), udev, NetworkManager dnsmasq
  catch-all, `walloftext-factory-reset`, `walloftext-reset-password`, `deploy.ps1` for Windows.
- The print document format (blocks) is in `docs/DOCUMENT.md`. Preview PNG == printed bitmap
  (golden tests), except the 180° rotation applied only on the way to the printer.

## 4. What has been built (all phases of BUILD_PLAN 0–8)

- **Phase 0** spike scripts + results (`spikes/`). Printer answered fully; button/LED/hotspot open.
- **Phase 1** password file + sign-in, Wi-Fi state machine (setup AP, fallback AP, reset by site,
  button hold or CLI), captive portal, setup/connected slips, install and factory-reset scripts.
- **Phase 2** renderer, queue, preview/print API, app shell, Create.
- **Phase 3** History, printer states, button gestures → actions, LED patterns.
- **Phase 4** scheduler (NTP wait, missed-run policy, quiet hours, holiday mode, daily limit,
  conditions), weather/calendar/Tasks/countdown sources, routines.
- **Phase 5** all Settings groups, guest page, shared "Waiting for your OK" list, backup/restore. Google sign-in inside the app (`docs/GOOGLE_SETUP.md`).
- **Phase 6** remote messages: email (IMAP app password) and Telegram bot, allowed senders,
  spoof check, never printed twice, approval, rate limits. SMS not built (paid). Setup steps:
  `docs/REMOTE_SETUP.md`.
- **Phase 7** Draw, Image, Templates (8 built-in), shared shopping list, quick-action chips, paper saver.
- **Phase 8** tablet/desktop layouts, accessibility (axe clean), watchdog (verified on the Pi),
  security headers, `tools/soak.py`.
- Phase 9 (master SD image) not started (optional).

## 5. Changes asked for after the build (all done, deployed and confirmed)

| Request | What changed |
|---|---|
| Use the design files, not my styling | `design-handoff/` copied into the repo; screens rebuilt to the mockups (paper-strip Create with Edit / As printed, 4-step schedule wizard, Up next timeline, receipt-grid History, device card, glass tab bar) |
| Printer connected: test and adapt | No-pause raster, darkness via `ESC 7`, automatic paper-out, clearer text (thin strokes widened, pixel fonts on their grid) |
| Remove the "sign" button | The "From" signature button, its sheet and the printed "from …" line are gone from Create |
| Fortune printing failed | Stale build metadata in `/opt` dropped `fortunes.json`; install now cleans and verifies |
| Reset hold 10 s → 30 s | Hold the button 30 s to restart Wi-Fi setup; 10 s is a normal long press |
| LED only at the start of a print | Driver waits for the physical print; LED/progress cover the whole print |
| Rotate every print 180° | Done, with a switch in Settings › Printer (on) |
| Fortune stars printed as crossed boxes | Stars and missing-character boxes are drawn as shapes (no font has ✱ or □) |

Deliberate deviations from the handoff (documented in `frontend/src/styles.css`): background blobs at
18 % opacity instead of 36 %, and small muted text `#A3A8B0` instead of `--muted`, both for contrast.
The shopping list lives in a sheet opened from its quick chip (the handoff has only four Create modes).

## 6. How to work on it

On the Pi, in `~/Wall_of_text`:

```bash
cd backend && ../.venv/bin/python -m pytest -q          # 139 tests
cd frontend && PATH=$HOME/.local/node/bin:$PATH npm run build
tools/smoke/run_server.sh &                              # mock backend on :8099
.venv/bin/python tools/smoke/smoke.py && .venv/bin/python tools/smoke/a11y.py
sudo bash deploy/install.sh --update                     # deploy to /opt and restart
```

Run locally with mock hardware: `WOT_HW=mock .venv/bin/python -m walloftext.app` (port 8080;
`/dev` is a dev panel; mock prints land in `backend/var/mock-printer/`).

Gotchas learned along the way:
- `sudo` asks for the password again in every new terminal tab.
- Files copied from Windows with `scp` arrive as `0600`; `install.sh` now makes `/opt` readable.
- `install.sh` deletes `backend/build` and `*.egg-info` before installing (stale ones once dropped
  `fortunes.json`) and fails if `fortunes.json` is missing afterwards.
- A full `install.sh` (no flag) ends in factory state and **forgets the home Wi-Fi**; it refuses to run
  without Ethernet unless `--force`. Use `--update` for normal deploys.
- The Imager Wi-Fi lives in netplan / cloud-init (`netplan-wlan0-*`, `/boot/firmware/network-config`);
  reset and factory reset remove those too.

## 7. Still open

- Wire and test the **button and LED** (`spikes/button_led_test.py`), including the 30 s reset hold.
- Try the **setup network and captive portal** with a phone (`spikes/hotspot_test.sh`, safe over Wi-Fi).
- Check `walloftext.local` from Windows, iPhone and Android.
- Connect real **Gmail / Telegram** accounts (`docs/REMOTE_SETUP.md`), weather place, and Google
  (Settings › Google, `docs/GOOGLE_SETUP.md`).
- Change the default passwords (`root` / `rootroot`) in Settings › Access.
- 24-hour soak (`tools/soak.py`) and 20 power cycles (`docs/PI_TESTING.md`).
- Optional: Phase 9 master image, SMS, HTTPS + service worker (not possible over plain HTTP).
