#!/usr/bin/env bash
# Marketing Bot launcher for Linux (Kali/Debian/Ubuntu). Builds the frontend,
# starts the single server on :8000 and opens the browser.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$ROOT/run.log"

echo "Marketing Bot starting (logs: $LOG)"

cd "$ROOT/frontend"
if ! npm run build >> "$LOG" 2>&1; then
  echo "Frontend build failed - see $LOG" >&2
  exit 1
fi
cd "$ROOT/backend"

command -v ./venv/bin/python >/dev/null || { echo "backend/venv missing - create it with: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2; exit 1; }
command -v pgrep >/dev/null || echo "warning: pgrep not found (install procps)"

nohup ./venv/bin/python main.py >> "$ROOT/backend.log" 2>&1 &
SERVER_PID=$!

for i in $(seq 1 120); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "Server is up (pid $SERVER_PID); opening browser..."
    command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 || true
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Server process exited - see $ROOT/backend.log" >&2
    exit 1
  fi
  sleep 1
done
echo "Server did not become healthy in 120s - see $ROOT/backend.log" >&2
exit 1
