#!/bin/sh
# Secure profile (ADR-0027): creates the Operaton engine users of the services and of the Godot task terminal
# with the built-in admin demo/demo. Passwords are local defaults (O34). Idempotent: existing users are kept.
# Authorization checks are not enabled (any engine user may use the whole REST API, open issue O58).
set -u
API=http://bpmn:8080/engine-rest
until curl -fsS -u demo:demo -o /dev/null "$API/engine"; do sleep 2; done
for user in mes sustainability maintenance erp godot; do
    code=$(curl -s -o /dev/null -w '%{http_code}' -u demo:demo -H 'Content-Type: application/json' \
        -X POST "$API/user/create" -d "{\"profile\": {\"id\": \"$user\", \"firstName\": \"$user\", \
\"lastName\": \"Virtual Factory\", \"email\": \"$user@virtual-factory.example\"}, \
\"credentials\": {\"password\": \"$user-local-secret\"}}")
    echo "bpmn-users: $user -> HTTP $code"
done
