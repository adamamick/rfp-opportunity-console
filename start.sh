#!/usr/bin/env bash
set -euo pipefail
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-10000}"
exec python3 src/dashboard_server.py --host "$HOST" --port "$PORT"
