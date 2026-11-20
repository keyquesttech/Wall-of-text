#!/usr/bin/env bash
# Phase 0 hotspot + captive-portal spike.
#
#   sudo bash spikes/hotspot_test.sh [--minutes 6]
#
# SAFE OVER WI-FI SSH: it runs itself in the background with nohup, raises
# WallOfText-Setup for N minutes (default 6), then drops the AP and brings
# your home Wi-Fi back by itself. Your SSH session will drop during the test;
# reconnect afterwards and read spikes/hotspot_test.log.
#
# While the AP is up, with your phone:
#   1. Join WallOfText-Setup, password rootroot. Note: did a captive sheet open?
#   2. Is the sheet showing the "Spike captive page"? Note iPhone vs Android.
#   3. From a PC on the AP:  ssh <user>@10.42.0.1   (works?)
# Everything the phones request is logged to spikes/captive_requests.log.
set -uo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/hotspot_test.log"
MIN=6
[[ "${1:-}" == --minutes ]] && MIN="${2:-6}"

if [[ "${WOT_SPIKE_CHILD:-}" != 1 ]]; then
  echo "Starting in the background for $MIN minutes. Log: $LOG"
  echo "Your SSH session will drop if you are on Wi-Fi. Reconnect in about $((MIN + 1)) minutes."
  WOT_SPIKE_CHILD=1 nohup bash "$0" --minutes "$MIN" >"$LOG" 2>&1 &
  exit 0
fi

ts() { date '+%H:%M:%S'; }
say() { echo "[$(ts)] $*"; }

HOME_CON="$(nmcli -t -f NAME,TYPE con show --active | awk -F: '$2=="802-11-wireless"{print $1; exit}')"
say "home Wi-Fi profile in use: ${HOME_CON:-none}"
say "radio: $(rfkill list wifi | tr '\n' ' ')"
say "iw interface combinations:"; iw list | grep -A4 'valid interface combinations'

say "Q: does NetworkManager refuse the 4-char password 'root'?"
if nmcli con add type wifi ifname wlan0 con-name wot-spike-short autoconnect no ssid WallOfText-Short \
     802-11-wireless.mode ap ipv4.method shared wifi-sec.key-mgmt wpa-psk wifi-sec.psk root >/dev/null 2>&1; then
  say "A: NO - it accepted 'root' (unexpected)"; nmcli con delete wot-spike-short >/dev/null
else
  say "A: yes, refused"
fi

say "scan before AP (cached by the app in real use):"
nmcli -t -f SSID,SIGNAL,SECURITY,FREQ dev wifi list --rescan yes | head -15

nmcli con delete wot-setup-ap >/dev/null 2>&1
nmcli con add type wifi ifname wlan0 con-name wot-setup-ap autoconnect no ssid WallOfText-Setup \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk rootroot >/dev/null && say "AP profile created"

install -d /etc/NetworkManager/dnsmasq-shared.d
cp "$DIR/../deploy/nm/wot-captive.conf" /etc/NetworkManager/dnsmasq-shared.d/wot-captive.conf
say "DNS catch-all installed"

python3 "$DIR/captive_probe_server.py" --log "$DIR/captive_requests.log" &
SRV=$!
sleep 1

restore() {
  say "restoring"
  kill $SRV 2>/dev/null
  nmcli con down wot-setup-ap >/dev/null 2>&1
  if [[ -n $HOME_CON ]]; then
    for i in 1 2 3; do
      nmcli --wait 40 con up "$HOME_CON" && break
      say "home Wi-Fi retry $i"; sleep 5
    done
  fi
  say "home link: $(nmcli -t -f GENERAL.CONNECTION,IP4.ADDRESS dev show wlan0 | tr '\n' ' ')"
  say "done"
}
trap restore EXIT

T0=$(date +%s)
say "AP up..."
nmcli con up wot-setup-ap && say "AP is up on 10.42.0.1" || { say "AP FAILED to start"; exit 1; }
pgrep -a dnsmasq | sed 's/^/    /'
say "DNS check: $(getent hosts example.com || echo none) (resolves via system resolver, not AP dnsmasq)"
say "dig against AP dnsmasq: $(command -v dig >/dev/null && dig +short @10.42.0.1 captive.apple.com || echo 'dig not installed')"

END=$((T0 + MIN * 60))
while (( $(date +%s) < END )); do
  n=$(iw dev wlan0 station dump | grep -c '^Station')
  say "stations on AP: $n"
  sleep 15
done

say "Q: can the AP be dropped and the client connection made, then the AP raised again?"
nmcli con down wot-setup-ap
if [[ -n $HOME_CON ]] && nmcli --wait 40 con up "$HOME_CON"; then
  say "client OK: $(nmcli -t -f IP4.ADDRESS dev show wlan0)"
  nmcli con up wot-setup-ap && say "AP raised again OK" || say "AP re-raise FAILED"
  sleep 10
fi
