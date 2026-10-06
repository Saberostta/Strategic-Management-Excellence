#!/usr/bin/env bash
# Weekly XRF report: processes the newest .xlsx in inbox/, accumulates history, writes to reports/.
set -euo pipefail
cd "$(dirname "$0")"
latest=$(ls -t inbox/*.xlsx 2>/dev/null | head -1 || true)
[ -n "$latest" ] || { echo "No .xlsx file found in inbox/"; exit 1; }
python3 -m xrf_report "$latest" --history data/history.csv -o reports
