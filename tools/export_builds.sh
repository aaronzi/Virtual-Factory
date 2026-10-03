#!/usr/bin/env bash
# Desktop builds (macOS universal .app in a zip, Windows x86_64 .exe, Linux x86_64) into build/.
# Needs the Godot export templates of the engine version (Editor > Manage Export Templates, or the .tpz from
# the Godot release extracted to ~/Library/Application Support/Godot/export_templates/<version>/).
# Usage: tools/export_builds.sh [macOS|Windows|Linux ...]   (default: all three)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
PRESETS=("$@")
[ ${#PRESETS[@]} -eq 0 ] && PRESETS=(macOS Windows Linux)
for preset in "${PRESETS[@]}"; do
  out=$(awk -v p="$preset" '/^name=/{n=$0} /^export_path=/{ if (n=="name=\""p"\"") {gsub(/export_path=|"/,""); print} }' export_presets.cfg)
  mkdir -p "$(dirname "$out")"
  echo "== $preset -> build/${out#../build/}"
  "$GODOT" --headless --export-release "$preset" "$out" 2>&1 | grep -vE "^$|Godot Engine" | tail -5
done
cd "$ROOT/build"
for dir in windows linux; do
  [ -d "$dir" ] && (cd "$dir" && zip -qr "../VirtualFactory-$dir.zip" .)
done
[ -f macos/VirtualFactory.zip ] && cp macos/VirtualFactory.zip VirtualFactory-macos.zip
ls -la "$ROOT/build"/*.zip
