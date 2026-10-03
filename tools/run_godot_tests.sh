#!/usr/bin/env bash
# Run all GUT unit tests headless. Fails on test failures AND on script/parse errors
# (GUT silently skips scripts that fail to load).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
LOG="$(mktemp)"
"$GODOT" --headless -s res://tests/compile_all.gd 2>&1 | tee "$LOG"
"$GODOT" --headless -s addons/gut/gut_cmdln.gd -gconfig=res://.gutconfig.json "$@" 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}
if grep -qE "SCRIPT ERROR|Parse Error|Failed to load script|compile_all: failed" "$LOG"; then
  echo "ERROR: script errors detected (see above)" >&2
  STATUS=1
fi
rm -f "$LOG"
exit "$STATUS"
