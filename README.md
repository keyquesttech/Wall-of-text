# Wall of Text

A thermal "wall printer" on a Raspberry Pi 4. Phones and laptops on the home
Wi-Fi open `http://walloftext.local/` to print notes, schedules and messages.

- Plan: [BUILD_PLAN.md](BUILD_PLAN.md) (backend, Pi, phases) and `design-handoff/HANDOFF.md` (UI spec, not in this repo yet)
- Project context / hand-over: [CONTEXT.md](CONTEXT.md)
- Progress: [docs/PROGRESS.md](docs/PROGRESS.md)
- Phase 0 hardware spikes: [spikes/README.md](spikes/README.md)
- What still needs trying on the real Pi: [docs/PI_TESTING.md](docs/PI_TESTING.md)
- Remote messages setup (Gmail, Telegram): [docs/REMOTE_SETUP.md](docs/REMOTE_SETUP.md)
- Print document format: [docs/DOCUMENT.md](docs/DOCUMENT.md)

## Layout

| Folder | What |
|---|---|
| `backend/` | FastAPI app (`walloftext/`) and tests |
| `setup-ui/` | Framework-free pages: Wi-Fi setup (captive portal), Sign in, guest note page, basic settings fallback, dev panel |
| `frontend/` | Preact + TypeScript + Vite app, built to `frontend/dist` (served by the backend) |
| `fonts/` | OFL fonts shared by the web UI and the print renderer |
| `deploy/` | `install.sh`, `deploy.ps1`, systemd, NetworkManager, polkit, udev, admin scripts |
| `spikes/` | Phase 0 scripts and `SPIKE_RESULTS.md` |

## Run it locally (mock hardware)

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e "backend[dev]"
WOT_HW=mock .venv/bin/python -m walloftext.app
```

Open `http://localhost:8080/`. The mock starts in setup mode with no Wi-Fi saved.
Fake networks: `HomeWiFi` / `correct-horse`. `/dev` is a dev panel that switches the
router off and on, puts a phone on the setup AP and fires button gestures. The mock
printer writes PNG and raw bytes to `backend/var/mock-printer/`.

On Windows use `.venv\Scripts\python` and `set WOT_HW=mock`.

Frontend (Node 18+; on this Pi Node lives in `~/.local/node`):

```bash
cd frontend && npm ci && npm run build
```

`npm run dev` serves the UI with hot reload and proxies `/api` to `localhost:8080`
(`WOT_BACKEND=http://walloftext.local npm run dev` to use the real Pi).

Tests:

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

End-to-end smoke test and accessibility check (Playwright + axe-core, mock backend on :8099):

```bash
tools/smoke/run_server.sh &
```
```bash
.venv/bin/python tools/smoke/smoke.py && .venv/bin/python tools/smoke/a11y.py
```

## Install on the Pi

On the Pi, from a checkout:

```bash
sudo deploy/install.sh
```

A full install ends in **factory state**: it forgets the home Wi-Fi and hosts
`WallOfText-Setup` (password `rootroot`). It refuses to run without Ethernet unless
you pass `--force`. `--keep-wifi` installs and stays on the current Wi-Fi.
From the PC afterwards: `.\deploy\deploy.ps1` (code update only).

Passwords: `/etc/walloftext/passwords.txt` (site `root`, setup Wi-Fi `rootroot`).
Recovery: `sudo walloftext-reset-password`. Full reset: `sudo walloftext-factory-reset`.
