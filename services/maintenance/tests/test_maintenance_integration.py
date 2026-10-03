"""Predictive maintenance loop against the running stack and a UNS-connected factory (`uv run pytest
-m integration`, ADR-0029): accelerated finger wear (UNS command RB01.finger_wear_rate) -> the maintenance
service predicts the end of life from the historian and opens a MaintenanceOrder -> the planning task
appears in Operaton -> the line stops in maintenance mode (order boundary, or immediately when the running
order still needs more than 4 parts) -> the technician task is completed -> the device's wear diagnostics
are reset through the Control Component -> the line is back in EXECUTE in the unit mode Production. Waits
at most ~12 minutes; skipped without a producing factory."""

from __future__ import annotations

import time

import httpx
import pytest

from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

pytestmark = pytest.mark.integration
MAINT, ERP, OPS = "http://localhost:8094", "http://localhost:8098", "http://localhost:8095"
BPMN = "http://localhost:8092/engine-rest"
NORMAL_RATE, FAST_RATE = 4e-10, 6e-5


def _get(url: str, **params):
    return httpx.get(url, params=params, timeout=10).json()


def _wait(what: str, condition, timeout_s: float, step_s: float = 3.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(step_s)
    raise AssertionError(f"timeout: {what}")


@pytest.fixture(scope="module")
def stack():
    try:
        health = _get(f"{MAINT}/health")
        settings = _get(f"{ERP}/api/settings")
    except httpx.HTTPError:
        pytest.skip("maintenance service / ERP not running")
    state = _get(f"{MAINT}/api/components/GR01")
    if state["prognosis"] is None:
        pytest.skip("no gripper history (factory not running?)")
    mqtt = MqttClient("vf-test-maintenance")
    if not mqtt.start(5):
        pytest.skip("broker not reachable")
    uns = Uns.load()
    httpx.put(f"{ERP}/api/settings", json={"standingQuantity": 2}, timeout=5)
    yield health, mqtt, uns
    mqtt.publish(uns.command("RB01", "finger_wear_rate"), {"v": NORMAL_RATE, "source": "test"})
    httpx.put(f"{ERP}/api/settings", json=settings, timeout=5)
    mqtt.stop()


def _task(key: str, definition: str) -> dict | None:
    instances = _get(f"{BPMN}/process-instance", businessKey=key, processDefinitionKey="MaintenanceOrder")
    if not instances:
        return None
    tasks = _get(f"{BPMN}/task", processInstanceId=instances[0]["id"], taskDefinitionKey=definition)
    return tasks[0] if tasks else None


def _complete(task: dict, variables: dict) -> None:
    typed = {k: {"value": v, "type": "Boolean" if isinstance(v, bool) else "String"}
             for k, v in variables.items()}
    response = httpx.post(f"{BPMN}/task/{task['id']}/complete", json={"variables": typed}, timeout=10)
    assert response.status_code == 204, response.text


def _parts_left() -> int:
    left = 0
    for order in _get(f"{ERP}/api/orders", state="InProcess"):
        quantity = int(order["SegmentRequirement"]["MaterialRequirement"][0]["Quantity"]["QuantityString"])
        left = max(left, quantity - order["Progress"]["Good"])
    return left


def test_accelerated_wear_is_predicted_maintained_and_production_restarts(stack):
    _, mqtt, uns = stack
    mqtt.publish(uns.command("RB01", "finger_wear_rate"), {"v": FAST_RATE, "source": "test"})
    key = _wait("maintenance order opened", lambda: _get(f"{MAINT}/api/orders").get("GR01"), 360, 5)
    assert _get(f"{MAINT}/health")["alarms"] == "901"
    plan = _wait("planning task in Operaton", lambda: _task(key, "User_Plan"), 60)
    assert "remaining useful life" in plan["description"]
    _complete(plan, {"immediate": _parts_left() > 4, "planner": "integration test"})
    mqtt.publish(uns.command("RB01", "finger_wear_rate"), {"v": NORMAL_RATE, "source": "test"})
    work = _wait("technician task (line in maintenance)", lambda: _task(key, "User_Execute"), 300, 5)
    gateway = _get(f"{OPS}/health")
    assert gateway["unit_mode"] == 2 and gateway["packml_state"] == 2, "STOPPED in the unit mode Maintenance"
    assert "Secure the robot cell" in work["description"]
    _complete(work, {"technician": "integration test", "findings": "pads worn", "partsReplaced": True})
    _wait("order closed", lambda: not _get(f"{MAINT}/api/orders").get("GR01"), 120)
    state = _get(f"{MAINT}/api/components/GR01")
    assert state["symptoms"]["GripCycles"] in (0, 1, 2, 3) and _get(f"{MAINT}/health")["alarms"] == ""
    _wait("line back in EXECUTE, unit mode Production",
          lambda: (lambda g: g["packml_state"] == 6 and g["unit_mode"] == 1)(_get(f"{OPS}/health")), 120)
