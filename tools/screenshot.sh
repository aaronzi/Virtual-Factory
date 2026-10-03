#!/usr/bin/env bash
# Capture a review screenshot of the Godot project without opening the editor.
# Usage: tools/screenshot.sh <output.png> [delay_seconds] [scene_res_path] [extra --vf-* args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
OUT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
DELAY="${2:-3}"
SCENE="${3:-}"
shift $(( $# < 3 ? $# : 3 ))
"$GODOT" --path "$ROOT/godot" --resolution 1600x900 ${SCENE:+"$SCENE"} -- \
  --vf-screenshot="$OUT" --vf-screenshot-delay="$DELAY" "$@"
