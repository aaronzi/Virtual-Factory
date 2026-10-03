"""Integration checks against the running compose stack (`uv run pytest -m integration`; Godot not required).

With the factory running the PackML call returns the real result; without it the ops gateway answers
`Accepted=false` with an explanation - either way the delegation BaSyx -> ops gateway works."""

from __future__ import annotations

import httpx
import pytest

from bridge.service import load_all
from mes.event_topics import discover
from ops_gateway.control import resolve
from vf_common import ids
from vf_common.basyx import BasyxClient

pytestmark = pytest.mark.integration
AAS_URL = "http://localhost:8091"


@pytest.fixture(scope="module")
def aas():
    client = BasyxClient(AAS_URL)
    try:
        client.list_shells(limit=1)
    except httpx.HTTPError:
        pytest.skip("compose stack not running")
    return client


def test_bridge_mappings_from_server(aas):
    mappings = load_all(aas)
    assert len(mappings) >= 100
    state = next(m for m in mappings if m.sink_path == "OperatingState" and "/PLC01/" in m.sink_submodel)
    assert state.transformation is not None and state.convert(6) == "Execute"


def test_line_control_operation_is_delegated(aas):
    line_control = ids.submodel_id("LINE01", "LineControl", "1")
    result = aas.invoke(line_control, "ExecutePackMLCommand", {"Command": "Jump"})
    assert result["success"] and result["Accepted"] == "false"
    assert "unknown command" in result["Message"]


def test_ops_gateway_health():
    response = httpx.get("http://localhost:8095/health", timeout=5)
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_gateway_endpoints_resolved_from_the_server(aas):
    """The running gateway uses exactly the topics the AAS on the server describes (CC -> AID)."""
    config = resolve(aas, ids.submodel_id("LINE01", "LineControl", "1"))
    health = httpx.get("http://localhost:8095/health", timeout=5).json()
    assert health["controller"] == config.controller
    for name, affordance in config.endpoints.items():
        assert health["endpoints"][name]["topic"] == affordance.form.topic
    # PLC01: OPC UA interface (ADR-0024) - synchronous method calls, no MQTT acknowledgement topic
    assert health["endpoints"]["PackMLCommand"]["protocol"] == "opcua"
    assert health["endpoints"]["PackMLCommand"]["topic"].endswith(";s=PLC01.Commands.packml_command")
    assert {"Produce", "ExchangeContainer"} <= set(health["skills"])


def test_execute_skill_is_delegated_and_validated(aas):
    line_control = ids.submodel_id("LINE01", "LineControl", "1")
    result = aas.invoke(line_control, "ExecuteSkill", {"Skill": "Fly", "Mode": "", "Parameters": ""})
    assert result["success"] and result["Accepted"] == "false" and "unknown skill 'Fly'" in result["Message"]
    result = aas.invoke(line_control, "ExecuteSkill",
                        {"Skill": "ExchangeContainer", "Mode": "", "Parameters": '{"container": 3}'})
    assert result["Accepted"] == "false" and "not one of" in result["Message"]


def test_mes_event_topics_from_the_aid(aas):
    topics = discover(aas)
    assert len(topics) >= 7 and "part_sorted" in topics.values()
