#!/usr/bin/env bash
# Wall of Text installer (BUILD_PLAN sections 2 and 13, Phase 1).
#
#   sudo deploy/install.sh              full install, ends in FACTORY STATE (home Wi-Fi forgotten)
#   sudo deploy/install.sh --update     copy new code + restart; keeps Wi-Fi, passwords and data
#   sudo deploy/install.sh --keep-wifi  full install but do NOT forget the home Wi-Fi
#
# Factory state = hostname walloftext, service enabled, setup-AP profile created,
# no home Wi-Fi saved, password file at defaults, empty history.
#
# Safety: a full install forgets the home Wi-Fi. If you are connected over Wi-Fi
# (no Ethernet carrier) it refuses unless you pass --force, so you don't cut
# your own SSH session off. After that, join WallOfText-Setup and use 10.42.0.1.
set -euo pipefail

MODE=full
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --update) MODE=update ;;
    --keep-wifi) MODE=keep-wifi ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/walloftext
ETC=/etc/walloftext
VAR=/var/lib/walloftext
SVC_USER=walloftext
PWFILE=$ETC/passwords.txt

say() { printf '\n== %s\n' "$*"; }

if [[ $MODE == full && $FORCE -eq 0 ]]; then
  if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null || echo 0)" != 1 ]]; then
    cat >&2 <<'EOF'
No Ethernet cable detected. A full install ends in factory state and FORGETS the
home Wi-Fi, which would cut this SSH session off.
  - plug in Ethernet and run again, or
  - run with --keep-wifi to install but stay on this Wi-Fi, or
  - run with --force, then join WallOfText-Setup (password rootroot) and ssh to 10.42.0.1
EOF
    exit 3
  fi
fi

if [[ $MODE != update ]]; then
  say "Packages"
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
    python3-venv python3-gpiozero python3-lgpio avahi-daemon iw network-manager rsync

  say "Hostname"
  if [[ "$(hostname)" != walloftext ]]; then
    hostnamectl set-hostname walloftext
    sed -i 's/^127\.0\.1\.1.*/127.0.1.1\twalloftext/' /etc/hosts
  fi
  systemctl enable --now avahi-daemon

  say "Wi-Fi country and radio"
  if command -v raspi-config >/dev/null; then raspi-config nonint do_wifi_country GB || true; fi
  rfkill unblock wifi || true

  say "Service user"
  id -u $SVC_USER >/dev/null 2>&1 || useradd --system --home-dir $VAR --shell /usr/sbin/nologin $SVC_USER
  for g in netdev gpio lp video dialout; do getent group $g >/dev/null && usermod -aG $g $SVC_USER; done
fi

if [[ -f "$SRC/frontend/package.json" && ! -f "$SRC/frontend/dist/index.html" ]]; then
  say "Frontend build"
  BUILD_USER="${SUDO_USER:-root}"
  NODE_DIR="$(getent passwd "$BUILD_USER" | cut -d: -f6)/.local/node/bin"
  if sudo -u "$BUILD_USER" env PATH="$NODE_DIR:$PATH" bash -c 'command -v npm' >/dev/null 2>&1; then
    sudo -u "$BUILD_USER" env PATH="$NODE_DIR:$PATH" bash -c "cd '$SRC/frontend' && npm ci --no-audit --no-fund && npm run build"
  else
    echo "WARNING: frontend/dist is missing and npm isn't installed. The site will show the basic"
    echo "         settings page only. Build on the PC with deploy/deploy.ps1, or install Node."
  fi
fi

say "Code -> $APP"
mkdir -p $APP
rsync -a --delete --exclude .git --exclude .venv --exclude 'backend/var' --exclude 'node_modules' \
  --exclude '__pycache__' --exclude 'frontend/src' --exclude 'tools/smoke/sample.jpg' --exclude venv --exclude 'backend/build' --exclude '*.egg-info' "$SRC"/ $APP/
if [[ ! -x $APP/venv/bin/python ]]; then
  python3 -m venv --system-site-packages $APP/venv
fi
$APP/venv/bin/pip install -q --upgrade pip
# stale build/ and egg-info make setuptools reuse an old file list (it once dropped fortunes.json)
rm -rf "$APP/backend/build" "$APP"/backend/*.egg-info
$APP/venv/bin/pip install -q --force-reinstall --no-deps "$APP/backend"
$APP/venv/bin/pip install -q "$APP/backend"
rm -rf "$APP/backend/build" "$APP"/backend/*.egg-info
PKG="$($APP/venv/bin/python -c 'import walloftext, os; print(os.path.dirname(walloftext.__file__))')"
[[ -f "$PKG/sources/fortunes.json" ]] || { echo "ERROR: installed package is missing sources/fortunes.json" >&2; exit 4; }
chown -R root:root $APP
# files copied from Windows (scp) can arrive as 0600; the service user must be able to read them
chmod -R u=rwX,go=rX $APP

say "Config and data dirs"
install -d -m 0750 -o $SVC_USER -g $SVC_USER $ETC
install -d -m 0750 -o $SVC_USER -g $SVC_USER $VAR
if [[ ! -f $PWFILE ]]; then
  $APP/deploy/bin/walloftext-reset-password --quiet
fi

say "System files"
install -m 0644 $APP/deploy/systemd/walloftext.service /etc/systemd/system/walloftext.service
install -d /etc/NetworkManager/dnsmasq-shared.d
install -m 0644 $APP/deploy/nm/wot-captive.conf /etc/NetworkManager/dnsmasq-shared.d/wot-captive.conf
install -m 0644 $APP/deploy/polkit/50-walloftext.rules /etc/polkit-1/rules.d/50-walloftext.rules
install -m 0644 $APP/deploy/udev/60-walloftext-printer.rules /etc/udev/rules.d/60-walloftext-printer.rules
install -m 0755 $APP/deploy/bin/walloftext-factory-reset /usr/local/sbin/walloftext-factory-reset
install -m 0755 $APP/deploy/bin/walloftext-reset-password /usr/local/sbin/walloftext-reset-password
install -d /etc/systemd/journald.conf.d
install -m 0644 $APP/deploy/journald/walloftext.conf /etc/systemd/journald.conf.d/walloftext.conf
systemctl restart systemd-journald || true
udevadm control --reload-rules && udevadm trigger --subsystem-match=usbmisc || true
systemctl daemon-reload

say "Setup network profile"
PSK="$(sed -n 's/^setup_wifi_password=//p' $PWFILE | head -1)"
[[ ${#PSK} -ge 8 ]] || PSK=rootroot
if nmcli -t -f NAME con show | grep -qx wot-setup-ap; then
  nmcli con modify wot-setup-ap wifi-sec.psk "$PSK"
else
  nmcli con add type wifi ifname wlan0 con-name wot-setup-ap autoconnect no ssid WallOfText-Setup \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" >/dev/null
fi
systemctl reload NetworkManager || true

systemctl enable walloftext.service

case $MODE in
  update|keep-wifi)
    systemctl restart walloftext.service
    say "Done. Service restarted. http://walloftext.local/"
    ;;
  full)
    say "Factory state"
    /usr/local/sbin/walloftext-factory-reset --yes
    ;;
esac
