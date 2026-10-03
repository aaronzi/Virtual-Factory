#!/usr/bin/env bash
# Run all GUT unit tests headless. Exit code != 0 on failures.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
"$GODOT" --headless -s addons/gut/gut_cmdln.gd -gconfig=res://.gutconfig.json "$@"
