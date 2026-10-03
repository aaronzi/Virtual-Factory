"""Alarm lifecycle against the running stack and factory (`uv run pytest -m integration`): a protective stop
injected over the UNS raises PLC alarm 201; the alarms service shows it UNACK, an operator acknowledges it
through the REST API, it returns to normal when released; journal, occurrence and KPIs are in TimescaleDB.
Skipped when the stack or a UNS-connected factory (Godot) is not running."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

pytestmark = pytest.mark.integration
API = "http://localhost:8099"


def _wait(predicate, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    return None


def _alarm(code: int) -> dict:
    alarms = httpx.get(f"{API}/api/alarms", params={"all": "true"}, timeout=5).json()
    return next((a for a in alarms if a["code"] == code), {})


@pytest.fixture(scope="module")
def mqtt():
    try:
        assert httpx.get(f"{API}/health", timeout=3).status_code == 200
    except (httpx.HTTPError, AssertionError):
        pytest.skip("alarms service not running")
    uns = Uns.load()
    client = MqttClient("vf-test-alarms", "localhost", 1883)
    client.subscribe(uns.status_topic, qos=1)
    if not client.start(5):
        pytest.skip("MQTT broker not reachable")
    status = client.get(timeout=3)
    if not status or (status.json() or {}).get("v") != "online":
        client.stop()
        pytest.skip("no UNS-connected factory (Godot) running")
    yield client, uns
    client.stop()


def test_alarm_raised_acknowledged_and_cleared(mqtt):
    client, uns = mqtt
    if _alarm(201).get("state") != "NORM":
        pytest.skip("alarm 201 is not in NORM (factory busy with another test)")
    topic = uns.command("RB01", "protective_stop")
    client.publish(topic, {"v": True, "source": "pytest"})
    try:
        raised = _wait(lambda: _alarm(201).get("state") == "UNACK" and _alarm(201))
        assert raised and raised["priority"] == "Medium" and raised["active"]
        ack = httpx.post(f"{API}/api/alarms/201/ack", json={"operator": "pytest", "comment": "integration"})
        assert ack.status_code == 200 and ack.json()["state"] == "ACKED"
    finally:
        client.publish(topic, {"v": False, "source": "pytest"})
    assert _wait(lambda: _alarm(201).get("state") == "NORM")
    journal = httpx.get(f"{API}/api/journal", params={"code": 201, "limit": 3}, timeout=5).json()
    assert [j["event"] for j in journal] == ["CLEARED", "ACKNOWLEDGED", "ACTIVATED"]
    assert journal[1]["operator"] == "pytest"
    kpis = httpx.get(f"{API}/api/kpis", params={"window": 10}, timeout=5).json()
    assert any(a["code"] == 201 for a in kpis["badActors"]) and kpis["meanTimeToAckS"] is not None
    commands = httpx.get(f"{API}/api/events", params={"kind": "command", "limit": 5}, timeout=5).json()
    assert any(json.dumps(c["payload"]).find("pytest") >= 0 for c in commands)
