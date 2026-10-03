#!/usr/bin/env bash
# Headless runs of the line with each training scenario (godot/config/scenarios/*.json); checks the expected
# effect in the PLC (rejects, alarms, HELD/ABORTED, recovery) - see godot/tests/integration/scenario_run.gd.
# Usage: [VF_SCENARIO_SECONDS=240] tools/run_scenarios.sh [scenario_id ...]   (default: all scenarios)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
SECONDS_SIM="${VF_SCENARIO_SECONDS:-240}"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
IDS=("$@")
if [ ${#IDS[@]} -eq 0 ]; then
  IDS=($(sed -n 's/.*"id": *"\([^"]*\)".*/\1/p' config/scenarios/*.json))
fi
STATUS=0
for id in "${IDS[@]}"; do
  echo "=== scenario $id ==="
  LOG="$(mktemp)"
  perl -e 'alarm 900; exec @ARGV' "$GODOT" --headless --fixed-fps 60 -s res://tests/integration/scenario_run.gd -- \
    --vf-scenario="$id" --vf-sim-seconds="$SECONDS_SIM" --vf-uns=off >"$LOG" 2>&1 || STATUS=1
  grep -E "^\[Scenario\]|SCENARIO RUN|SCRIPT ERROR" "$LOG"
  rm -f "$LOG"
done
exit "$STATUS"
