#!/usr/bin/env bash
# Start a throwaway mock backend for smoke tests: fresh data dir, router on, one saved network.
set -e
cd "$(dirname "$0")/../.."
D=${WOT_DATA_DIR:-/tmp/wot-smoke}
rm -rf "$D"; mkdir -p "$D"
export WOT_HW=mock WOT_PORT=${WOT_PORT:-8099} WOT_DATA_DIR=$D WOT_PASSWORD_FILE=$D/passwords.txt WOT_MOCK_BAND_DELAY=${WOT_MOCK_BAND_DELAY:-0.03} WOT_MOCK_ONLINE=1
exec .venv/bin/python -m walloftext.app
