#!/usr/bin/env bash
# Render actual frames; headless runs cannot measure GPU performance.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
OUT="$ROOT/build/visual-review"
mkdir -p "$OUT"
DRAW_BUDGET=(350 550 650)
PRIMITIVE_BUDGET=(125000 250000 350000)
for quality in 0 1 2; do
  perl -e 'alarm 60; exec @ARGV; die $!' "$GODOT" --path "$ROOT/godot" --resolution 1920x1080 \
    --script res://tests/tools/render_benchmark.gd -- \
    --vf-uns=off --vf-backplane=off --vf-aas-events=off --vf-retain=off --vf-quality="$quality" \
    --vf-perf-warmup=5 --vf-perf-report=10 "$@" > "$OUT/quality-$quality.log" 2>&1
  rg 'VisualBenchmark|PERF' "$OUT/quality-$quality.log"
  metrics="$(rg 'PERF' "$OUT/quality-$quality.log")"
  [[ "$metrics" =~ max_draw_calls=([0-9]+) ]]
  draws="${BASH_REMATCH[1]}"
  [[ "$metrics" =~ max_primitives=([0-9]+) ]]
  primitives="${BASH_REMATCH[1]}"
  if (( draws > DRAW_BUDGET[quality] || primitives > PRIMITIVE_BUDGET[quality] )); then
    echo "Visual budget exceeded for quality $quality: $draws draws / $primitives primitives" >&2
    exit 1
  fi
  if rg -q 'SCRIPT ERROR|ERROR:|Leaked instance' "$OUT/quality-$quality.log"; then
    cat "$OUT/quality-$quality.log"
    exit 1
  fi
done
