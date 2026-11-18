#!/usr/bin/env bash
# Marketing Bot stopper for Linux: kill the backend and anything serving :8000.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PIDS=$(pgrep -f "venv/bin/python main.py" || true)
if [ -n "$PIDS" ]; then
  echo "Stopping Marketing Bot: $PIDS"
  kill $PIDS 2>/dev/null || true
  sleep 1
  kill -9 $PIDS 2>/dev/null || true
else
  echo "No Marketing Bot backend process found."
fi

if command -v fuser >/dev/null; then
  fuser -k 8000/tcp 2>/dev/null || true
else
  PID_ON_8000=$( (command -v ss >/dev/null && ss -lptn 'sport = :8000' 2>/dev/null) | grep -oP '(?<=pid=)\d+' | head -1 || true)
  [ -n "$PID_ON_8000" ] && kill -9 "$PID_ON_8000" 2>/dev/null || true
fi
echo "Stopped."
