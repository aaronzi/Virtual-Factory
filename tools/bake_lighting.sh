#!/usr/bin/env bash
# Bake the static lighting of a layout (ADR-0031, docs/development.md "Baked lighting").
#   1. headless: build the main scene as at runtime, write the bake scene + manifest (bake_scene_builder.gd)
#   2. editor with Forward+ (opens a window for about a minute): LightmapGI bake via addons/vf_lightmap_bake
#   3. restore project.godot and other import settings the editor rewrites (texture "detect 3D"), re-import
# Usage: tools/bake_lighting.sh [layout name, default line1]  (output: godot/world/lighting/baked/<name>/)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
NAME="${1:-line1}"
DIR="res://world/lighting/baked/$NAME"
OUT="$ROOT/godot/world/lighting/baked/$NAME"
cd "$ROOT/godot"
"$GODOT" --headless --import >/dev/null 2>&1 || true
perl -e 'alarm 180; exec @ARGV' "$GODOT" --headless --script res://world/lighting/bake_scene_builder.gd -- \
  --vf-bake-main=res://factory/main.tscn --vf-bake-dir="$DIR" --vf-baked-lighting=off --vf-ui=off \
  --vf-uns=off --vf-backplane=off --vf-aas-events=off --vf-retain=off 2>&1 | grep -E "BakeScene|ERROR"
IMPORTS="$(mktemp)"
{ echo ./project.godot; find . -name "*.import" -not -path "./.godot/*" -not -path "./world/lighting/baked/*"; } \
  | tar cf "$IMPORTS" -T -
rm -f "$OUT"/lighting.lmbake
perl -e 'alarm 1800; exec @ARGV' "$GODOT" --editor --rendering-method forward_plus -- \
  --vf-bake-scene="$DIR/bake_scene.scn" --vf-bake-output="$DIR/lighting.lmbake" 2>&1 \
  | grep -E "LightmapBake|ERROR|Done baking" || true
tar xf "$IMPORTS" && rm -f "$IMPORTS"
"$GODOT" --headless --import >/dev/null 2>&1 || true
test -f "$OUT/lighting.lmbake" || { echo "bake failed: no $OUT/lighting.lmbake" >&2; exit 1; }
du -ch "$OUT"/lighting* "$OUT"/meshes/* | tail -n 1
