# What to try on the real Pi

Everything below has been built and tested against mock hardware. These are the checks that need
the real printer, button, phones or a power switch. Results go in `spikes/SPIKE_RESULTS.md`
(hardware) or `docs/PROGRESS.md`.

## 1. Update the Pi

On the Pi, from `~/Wall_of_text`:

```bash
git pull
```
```bash
sudo bash deploy/install.sh --update
```

From Windows instead: `.\deploy\deploy.ps1` (builds the frontend if Node is installed).
If you build on the Pi, the frontend needs `frontend/dist`. This Pi has Node in `~/.local/node`:

```bash
cd frontend && PATH=$HOME/.local/node/bin:$PATH npm ci && PATH=$HOME/.local/node/bin:$PATH npm run build
```

## 2. Phase 0 hardware spikes

Follow [spikes/README.md](../spikes/README.md): printer probe, button and LED, hotspot and captive
portal (safe over Wi-Fi; it restores your Wi-Fi itself), `.local` from each device.
Then update the printer udev rule with the vendor/product ID, and set the band size, pause and
density command the probe found (`printer/drivers.py`).

## 3. Phase 1 "done when" (needs Ethernet or `--force`, and a phone)

1. `sudo walloftext-factory-reset` (or a full `sudo deploy/install.sh` with Ethernet plugged in).
2. Phone: join **WallOfText-Setup** (password `rootroot`). The setup page should open by itself.
3. Pick your Wi-Fi, enter its password. The printer prints "Connected" with its address and IP.
4. Phone back on home Wi-Fi: `http://walloftext.local/` shows Sign in; `root` works, a wrong
   password doesn't.
5. Edit `gui_password` in `/etc/walloftext/passwords.txt`: the old password stops working within
   seconds, no restart.
6. Change the setup Wi-Fi password in Settings › Access, then Settings › Wi-Fi › Forget: the setup
   network uses the new password.
7. Hold the button 10 s: the light blinks three times; let go: setup network again.
8. Power cycle with the router off, switch the router on: the printer rejoins within about two minutes.

## 4. Printing (needs the printer)

- Settings › Printer › Print a test page. Then Create › Text, Draw, Image, Templates, List.
- Compare the paper with "As printed" on screen: they should match dot for dot.
- Open the lid mid-print: if the printer can't report paper-out (Phase 0 answer), use
  "Out of paper" in the status sheet; jobs wait and resume after "New roll".
- Unplug the printer's USB while printing: the job shows "Failed" with Try again, never auto-reprints.

## 5. Connections (needs accounts)

- Weather: Settings › Connections › Weather, type your town.
- Calendar: paste the Google Calendar "Secret address in iCal format".
- Google Tasks: run `tools/google_auth.py` on the PC and upload the token.
- Remote messages: follow [REMOTE_SETUP.md](REMOTE_SETUP.md) (Gmail app password, Telegram bot).
  Done when an allowed email and an allowed Telegram message print within ~90 s, a stranger's
  doesn't, the bot replies "Printed", and quiet hours hold messages.

## 6. Phase 8 endurance

- **24-hour soak** (needs ~1.5 m of paper), on the Pi:
  ```bash
  python3 tools/soak.py --hours 24
  ```
  Pass: no failed jobs, no service restarts, memory roughly flat, temperature below ~75 °C.
- **20 power cycles**: pull the power at random moments (idle, mid-print, during a schedule).
  After each: the site comes back, a job cut off mid-print shows "Failed (interrupted)" and is not
  reprinted, schedules missed while off follow the "If the printer was off" setting.
- **Watchdog**: `sudo kill -STOP $(systemctl show -p MainPID --value walloftext)`; within about a
  minute systemd restarts the service (`systemctl show walloftext -p NRestarts`). Then
  `sudo systemctl restart walloftext`.

## 7. Phones

- iPhone: Safari › Share › Add to Home Screen. It should open full-screen (no service worker over
  plain HTTP, so it needs the Pi to be on).
- Android: Chrome offers a shortcut, not a full install (needs HTTPS).
- If `walloftext.local` doesn't open on an older Android phone, use the IP shown in Settings › Wi-Fi.
