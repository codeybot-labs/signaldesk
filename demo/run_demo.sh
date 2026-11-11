#!/usr/bin/env bash
# Offline reproducible demo: scan cached fixtures, score, draft, approve one lead, write the board.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SIGNALDESK_OFFLINE=1
export SIGNALDESK_SKIP_MX=1
export SIGNALDESK_FIXTURE_DIR="${SIGNALDESK_FIXTURE_DIR:-$ROOT/tests/fixtures}"
export SIGNALDESK_DATA_DIR="${SIGNALDESK_DATA_DIR:-$ROOT/demo/out/data}"
mkdir -p "$ROOT/demo/out"
# Fresh board each run (keep it deterministic for recordings).
rm -rf "$SIGNALDESK_DATA_DIR"
python3 "$ROOT/demo/run_demo.py"
echo
echo "Board file: $ROOT/demo/out/board.html"
echo "For the interactive demo (Approve / Copy / Open .eml):"
echo "  python3 $ROOT/demo/serve_demo.py"
echo "  open http://127.0.0.1:8765/board.html"
echo "file://$ROOT/demo/out/board.html also works, with approve simulated locally."
