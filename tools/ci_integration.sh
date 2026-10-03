#!/usr/bin/env bash
# Integration suite end to end (CI workflow "Integration", also for local use; docs/development.md):
#   fresh compose stack (base + infra/docker-compose.ci.yml) -> readiness gate -> factory session 1
#   (headless Godot, UNS + PLC backplane) until a part is shipped -> session 2 -> factory gate ->
#   `pytest -m integration` -> skip check (a skip is a failure) -> logs -> teardown.
# Usage: tools/ci_integration.sh [extra pytest args]
#   GODOT_PATH         Godot 4.7.2 binary (default: /Applications/Godot.app/Contents/MacOS/Godot)
#   VF_CI_NO_BUILD=1   use the existing vf-services:dev image (the workflow builds it with the buildx cache)
#   VF_CI_KEEP=1       leave the stack running afterwards (default: down)
#   VF_CI_ALLOW_SKIP   space-separated test id substrings that may skip (default: none)
#   VF_CI_ARTIFACTS    logs and JUnit report (default: build/ci-integration)
#   VF_CI_SESSION1_S   length of factory session 1 in seconds (default 180; the first part ships after ~1 min)
# Uses the compose project "vf" and its host ports (the tests address localhost): it replaces a running vf
# stack. Exit code: 0 only if every integration test passed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT_PATH:-/Applications/Godot.app/Contents/MacOS/Godot}"
OUT="${VF_CI_ARTIFACTS:-$ROOT/build/ci-integration}"
COMPOSE=(docker compose -f infra/docker-compose.yml -f infra/docker-compose.ci.yml)
export VF_CI_COMPOSE="${COMPOSE[*]}"
SESSION1_S="${VF_CI_SESSION1_S:-180}"
GODOT_PID=""
GROUP=0
START=$(date +%s)
cd "$ROOT"
mkdir -p "$OUT"
rm -f "$OUT"/*.log "$OUT"/junit.xml "$OUT"/ps.txt

step() {  # collapsible sections in the GitHub log
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    [ "$GROUP" = 1 ] && echo "::endgroup::"
    echo "::group::$*"
    GROUP=1
  fi
  echo "=== [$(($(date +%s) - START)) s] $*"
}

with_timeout() {  # seconds, command... (macOS has no coreutils timeout)
  perl -e '$s = shift; alarm $s; exec @ARGV or die "exec: $!"' "$@"
}

start_factory() {  # session number, wall-clock seconds
  "$GODOT" --headless --max-fps 60 --path "$ROOT/godot" -- --vf-quit-after="$2" >"$OUT/godot-session$1.log" 2>&1 &
  GODOT_PID=$!
}

stop_factory() {
  if [ -n "$GODOT_PID" ]; then
    kill "$GODOT_PID" 2>/dev/null || true
    wait "$GODOT_PID" 2>/dev/null || true
    GODOT_PID=""
  fi
}

finish() {
  local status=$?
  stop_factory
  step "collect logs (exit $status)"
  "${COMPOSE[@]}" ps -a >"$OUT/ps.txt" 2>&1 || true
  "${COMPOSE[@]}" logs --no-color --timestamps >"$OUT/compose.log" 2>&1 || true
  if [ "${VF_CI_KEEP:-0}" != 1 ]; then
    step "teardown"
    "${COMPOSE[@]}" --profile '*' down --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ "$GROUP" = 1 ]; then echo "::endgroup::"; fi
  echo "ci_integration: exit $status after $(($(date +%s) - START)) s (logs: $OUT)"
  exit "$status"
}
trap finish EXIT

step "build and start the stack (fresh tmpfs databases)"
"${COMPOSE[@]}" --profile '*' down --remove-orphans
[ "${VF_CI_NO_BUILD:-0}" = 1 ] || "${COMPOSE[@]}" build provisioner
"${COMPOSE[@]}" up -d --quiet-pull
"$GODOT" --headless --path "$ROOT/godot" --import >"$OUT/godot-import.log" 2>&1 || true
uv run tools/ci_integration.py stack --timeout 600

step "factory session 1: ${SESSION1_S} s, then a part must be shipped (passport Active)"
start_factory 1 "$SESSION1_S"  # quits by itself: Godot ends on SIGTERM without saving the serial counter
with_timeout $((SESSION1_S + 120)) bash -c "while kill -0 $GODOT_PID 2>/dev/null; do sleep 2; done"
wait "$GODOT_PID" || true
GODOT_PID=""
uv run tools/ci_integration.py shipped --timeout 60

step "factory session 2: linked, producing, all test preconditions met"
start_factory 2 5400
uv run tools/ci_integration.py factory --timeout 600

step "pytest -m integration"
PYTHON="$(uv run python -c 'import sys; print(sys.executable)')"  # direct child: the timeout reaches pytest
set +e
with_timeout 3000 "$PYTHON" -m pytest -m integration -rs -v --durations=15 --junitxml="$OUT/junit.xml" "$@"
TESTS=$?
set -e
kill -0 "$GODOT_PID" 2>/dev/null || { echo "factory (Godot) died during the tests" >&2; TESTS=1; }

step "skip check"
ALLOW=()
for pattern in ${VF_CI_ALLOW_SKIP:-}; do ALLOW+=(--allow "$pattern"); done
uv run tools/ci_integration.py skips "$OUT/junit.xml" "${ALLOW[@]+"${ALLOW[@]}"}" || TESTS=1
exit "$TESTS"
