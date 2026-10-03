#!/bin/sh
# Starts Grafana and applies the org settings that file provisioning cannot express (ADR-0022): organisation
# name "Virtual Factory" (anonymous viewers join it), local user "editor" (role Editor) and the home dashboard
# LINE01 live. All calls are idempotent; a failure (e.g. admin password changed in the UI) is only logged.
set -u
API=http://127.0.0.1:3000/api
AUTH="${GF_SECURITY_ADMIN_USER:-admin}:${GF_SECURITY_ADMIN_PASSWORD}"

/run.sh "$@" &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null' TERM INT

api() {
    curl -fsS -o /dev/null -u "$AUTH" -H 'Content-Type: application/json' "$@" 2>/dev/null \
        || echo "vf-init: $2 $3 skipped (already applied or admin password changed)"
}

until curl -fsS "$API/health" >/dev/null 2>&1; do
    kill -0 "$pid" 2>/dev/null || exit 1
    sleep 1
done
api -X PUT "$API/orgs/1" -d '{"name": "Virtual Factory"}'
api -X POST "$API/admin/users" \
    -d "{\"name\": \"Editor\", \"login\": \"editor\", \"password\": \"${VF_GRAFANA_EDITOR_PASSWORD}\"}"
editor_id=$(curl -fsS -u "$AUTH" "$API/users/lookup?loginOrEmail=editor" 2>/dev/null \
    | sed -n 's/.*"id":\([0-9]*\).*/\1/p')
[ -n "$editor_id" ] && api -X PATCH "$API/org/users/$editor_id" -d '{"role": "Editor"}'
api -X PUT "$API/org/preferences" -d '{"homeDashboardUID": "vf-line01-live"}'
echo "vf-init: done"

while kill -0 "$pid" 2>/dev/null; do
    wait "$pid"
done
wait "$pid"
