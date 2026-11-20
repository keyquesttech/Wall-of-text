#!/usr/bin/env bash
# Stop whatever listens on the smoke-test port (default 8099).
PORT=${WOT_PORT:-8099}
for pid in $(ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
  kill "$pid" 2>/dev/null
done
exit 0
