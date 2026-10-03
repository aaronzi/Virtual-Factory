#!/usr/bin/env bash
# Headless, faster-than-real-time integration run of the whole line (default 600 simulated seconds).
# Usage: tools/run_line_simulation.sh [sim_seconds]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
"$GODOT" --headless --fixed-fps 60 -s res://tests/integration/line_run.gd -- --vf-sim-seconds="${1:-600}"
