#!/usr/bin/env bash
# Current visual documentation. Historical m0..m9 screenshots remain milestone evidence.
# Backend-backed inspector/data-flow screenshots need the local stack to be available.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMMON=(--vf-uns=off --vf-backplane=off --vf-aas-events=off --vf-retain=off)
capture() {
  local file="$1"
  shift
  perl -e 'alarm 70; exec @ARGV; die $!' tools/screenshot.sh "docs/screenshots/$file.png" 12 '' \
    "${COMMON[@]}" "$@"
}
capture factory-high --vf-quality=2
capture factory-medium --vf-quality=1
capture factory-low --vf-quality=0
capture factory-line --vf-quality=2 --vf-ui=off --vf-overlay=off
capture factory-inspector --vf-quality=2 --vf-inspect=RB01
capture factory-dataflow --vf-quality=1 --vf-dataflow
capture factory-quality-menu --vf-quality=2 --vf-menu
capture factory-robot --vf-quality=2 --vf-camera=1.4,1.7,1.2,0.25,0.6,-0.55
