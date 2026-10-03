"""PackML rules and the command round trip against a simulated controller (no broker needed); topics, nodes,
keys and skills come from the AAS built by the provisioner (Control Component -> AID), not from uns.json.

PLC01's Control Component points to its OPC UA interface (ADR-0024, see test_opcua_path.py). The MQTT
command path - still used for controllers without an OPC UA server - is tested here with `config`: the same
AAS with the endpoints re-pointed to the MQTT interface of the AID."""

from __future__ import annotations

import copy
import dataclasses
import json
import queue

import pytest

from ops_gateway import packml
from ops_gateway.control import resolve
from ops_gateway.gateway import LineGateway, Result
from ops_gateway.server import health, input_arguments, output_variables
from ops_gateway.skills import SkillExecutor
from provisioner.build import build
from vf_common import ids
from vf_common.aid import InMemoryAas
from vf_common.mqtt import Message
from vf_common.packml import UNIT_MODE_CHANGE_STATES

STATE = {name: i for i, name in enumerate(packml.STATES)}
LINE_CONTROL = ids.submodel_id("LINE01", "LineControl", "1")


@pytest.fixture(scope="module")
def env():
    return build().environment


@pytest.fixture(scope="module")
def opcua_config(env):
    return resolve(InMemoryAas(env), LINE_CONTROL)


@pytest.fixture(scope="module")
def config(env):
    """Endpoints re-pointed to the MQTT interface (a controller without OPC UA server)."""
    return resolve(InMemoryAas(mqtt_variant(env)), LINE_CONTROL)


def mqtt_variant(env: dict) -> dict:
    cc_id = ids.submodel_id("PLC01", "ControlComponentInstance", "2")
    variant = copy.deepcopy(env)
    variant["submodels"] = [json.loads(json.dumps(s).replace('"InterfaceOPCUA"', '"InterfaceMQTT"'))
                            if s["id"] == cc_id else s for s in variant["submodels"]]
    return variant


class FakeController:
    """Stands in for broker + Godot gateway: acknowledges commands on the AID ack topic and walks through
    PackML states on the AID state topic."""

    def __init__(self, config, state: str, auto_start: bool = True, accept: bool = True):
        self.config, self.auto_start, self.accept = config, auto_start, accept
        self.messages: queue.Queue[Message] = queue.Queue()
        self.published, self.subscribed = [], set()
        self.state, self.unit_mode = state, 1
        self._state(state)
        self._value("UnitMode", 1)

    def subscribe(self, topic, qos=1):
        self.subscribed.add(topic)

    def unsubscribe(self, topic):
        self.subscribed.discard(topic)

    def get(self, timeout=None):
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def publish(self, topic, payload, qos=1, retain=False):
        self.published.append((topic, payload, qos))
        action = next((a for a in self.config.endpoints.values() if a.form.topic == topic), None)
        if action is None or action.ack is None:
            return  # nobody listens (e.g. changed href)
        ack = {"corr": payload["corr"], "accepted": self.accept, "v": payload["v"]}
        if not self.accept:
            ack["reason"] = "not writable"
        self.messages.put(Message(action.ack.topic, json.dumps(ack).encode()))
        if self.accept and action.name == "packml_command":
            for state in self._walk(payload["v"]):
                self._state(state)
        if self.accept and action.name == "unit_mode_command" and self.state in UNIT_MODE_CHANGE_STATES:
            self.unit_mode = payload["v"]
            self._value("UnitMode", payload["v"])

    def _walk(self, command: int) -> list[str]:
        name = next(k for k, v in packml.COMMANDS.items() if v == command)
        target = packml.TARGET[name]
        return [target, "STARTING", "EXECUTE"] if target == "IDLE" and self.auto_start else [target]

    def _state(self, name: str) -> None:
        self.state = name
        self._value("PackMLState", STATE[name])

    def _value(self, endpoint: str, value) -> None:
        payload = json.dumps({"v": value, "ts": "t"}).encode()
        self.messages.put(Message(self.config.endpoints[endpoint].form.topic, payload))


def _gateway(config, state: str, **kw) -> tuple[LineGateway, FakeController]:
    fake = FakeController(config, state, **kw)
    gw = LineGateway(fake, config, ack_timeout=1.0, state_timeout=1.0)
    gw.start()
    assert gw._wait_for(lambda: gw.state == STATE[state], 1.0)
    return gw, fake


def test_endpoints_resolved_from_control_component_and_aid(opcua_config):
    """PLC01: OPC UA forms of the AID (href = node in the server namespace, base = server endpoint)."""
    command, state = opcua_config.endpoints["PackMLCommand"], opcua_config.endpoints["PackMLState"]
    assert (command.kind, command.name, command.protocol) == ("action", "packml_command", "opcua")
    assert command.base == "opc.tcp://localhost:4840/vf/plc01" and command.form.op == "invokeaction"
    assert command.form.topic == \
        "?id=nsu=urn:virtual-factory:plant01:line01:plc01;s=PLC01.Commands.packml_command"
    assert command.form.browse_path == "/0:Objects/2:PLC01/2:Commands/2:packml_command"
    assert command.ack is None, "synchronous: the result is the status code of the call"
    assert state.form.topic.endswith(";s=PLC01.Status.StateCurrent") and state.protocol == "opcua"
    assert opcua_config.endpoints["UnitModeCommand"].name == "unit_mode_command"
    assert opcua_config.endpoints["UnitMode"].form.topic.endswith(";s=PLC01.Status.UnitModeCurrent")


def test_mqtt_endpoints_resolved_from_control_component_and_aid(config):
    root = "vf/plant01/final-assembly/line01/plc01/"
    assert config.controller == "PLC01_LineController"
    command = config.endpoints["PackMLCommand"]
    assert (command.kind, command.name) == ("action", "packml_command")
    assert command.form.topic == root + "cmd/packml_command"
    assert command.form.qos == 1 and not command.form.retain and command.form.op == "invokeaction"
    assert command.key("Value", "") == "v" and command.key("CorrelationId", "") == "corr"
    assert command.ack.topic == root + "cmd-resp/packml_command" and command.ack.op == "queryaction"
    assert command.ack_key("Accepted", "") == "accepted"
    assert config.endpoints["ContainerExchange"].name == "klt_exchange_command"
    assert config.endpoints["AutoExchange"].form.topic == root + "cmd/auto_exchange"
    state = config.endpoints["PackMLState"]
    assert (state.kind, state.form.topic, state.form.retain, state.key("Value", "")) == \
        ("property", root + "packml_state", True, "v")
    assert ids.submodel_id("PLC01", "AssetInterfacesDescription", "1") in config.sources


def test_skills_resolved_from_control_component(config):
    produce, exchange = config.skills["Produce"], config.skills["ExchangeContainer"]
    assert produce.modes == ["Production", "Maintenance", "Manual"] and not produce.disabled
    assert set(produce.endpoints) == {"PackMLCommand", "PackMLState", "AutoExchange"}
    assert exchange.endpoints == ["ContainerExchange"]
    container = exchange.parameters["container"]
    assert container.convert("2") == 2
    with pytest.raises(ValueError, match="not one of 1 \\(KLT_A\\), 2 \\(KLT_B\\)"):
        container.convert(3)
    with pytest.raises(ValueError, match="outside Max"):
        produce.parameters["klt_capacity"].convert(13)


def test_rules():
    assert packml.check("Start", "IDLE") is None
    assert "not allowed in state STOPPED (allowed: Abort, Reset)" in packml.check("Start", "STOPPED")
    assert "unknown command" in packml.check("Jump", "IDLE")


def test_hold_round_trip(config):
    gw, fake = _gateway(config, "EXECUTE")
    result = gw.packml_command("Hold")
    assert result.accepted and result.state == "HELD"
    topic, payload, qos = fake.published[0]
    assert topic.endswith("/plc01/cmd/packml_command") and payload["v"] == 4 and qos == 1
    assert config.endpoints["PackMLCommand"].ack.topic in fake.subscribed


def test_reset_with_auto_start_sees_transient_idle(config):
    gw, _ = _gateway(config, "STOPPED")
    result = gw.packml_command("Reset")
    assert result.accepted, result.message


def test_rejections(config):
    gw, fake = _gateway(config, "STOPPED")
    assert not gw.packml_command("Hold").accepted and not fake.published
    gw2, _ = _gateway(config, "EXECUTE", accept=False)
    assert gw2.set_auto_exchange(False).message == "not writable"
    assert "not one of" in SkillExecutor(gw2).execute("ExchangeContainer", "", {"container": 3}).message


def test_unconfigured_gateway_rejects(config):
    gw = LineGateway(FakeController(config, "EXECUTE"))
    assert "not configured" in gw.packml_command("Hold").message
    assert "not configured" in SkillExecutor(gw).execute("Produce").message
    assert health(gw)["status"] == "unconfigured"


def test_reconfiguration_follows_a_changed_href(config):
    gw, fake = _gateway(config, "EXECUTE")
    old = config.endpoints["PackMLCommand"]
    moved = dataclasses.replace(old, form=dataclasses.replace(old.form, topic="vf/test/moved"),
                                ack=dataclasses.replace(old.ack, topic="vf/test/moved-resp"))
    gw.configure(dataclasses.replace(config, endpoints={**config.endpoints, "PackMLCommand": moved}))
    assert "vf/test/moved-resp" in fake.subscribed and old.ack.topic not in fake.subscribed
    result = gw.packml_command("Hold")
    assert fake.published[-1][0] == "vf/test/moved" and not result.accepted  # nobody acknowledges there


def test_execute_skill_produce(config):
    gw, fake = _gateway(config, "ABORTED", auto_start=False)
    result = SkillExecutor(gw, auto_start_wait=0.2).execute("Produce", "", '{"auto_exchange": false}')
    assert result.accepted and result.state == "EXECUTE", result.message
    assert "Clear -> Reset -> Start" in result.message and "(Production)" in result.message
    assert [p[0].rsplit("/", 1)[-1] for p in fake.published] == \
        ["auto_exchange", "packml_command", "packml_command", "packml_command"]
    assert SkillExecutor(gw).execute("Produce").message.endswith("already in EXECUTE)")


def test_execute_skill_produce_with_auto_start(config):
    gw, fake = _gateway(config, "STOPPED")
    result = SkillExecutor(gw).execute("Produce", "Production")
    assert result.accepted and "(Reset)" in result.message and len(fake.published) == 1


def test_execute_skill_validation(config):
    gw, fake = _gateway(config, "EXECUTE")
    skills = SkillExecutor(gw)
    assert "unknown skill 'Fly'" in skills.execute("Fly").message
    assert "mode 'Turbo' not offered" in skills.execute("Produce", "Turbo").message
    assert "unknown parameter 'speed'" in skills.execute("Produce", "", {"speed": 1}).message
    assert "is an output" in skills.execute("Produce", "", {"parts_ok": 1}).message
    assert "cannot be set at runtime" in skills.execute("Produce", "", {"belt_speed": 0.2}).message
    assert "not a JSON object" in skills.execute("Produce", "", "speed=1").message
    assert not fake.published
    assert "stop the line first" in skills.execute("ExchangeContainer", "Manual", '{"container": 2}').message
    assert not fake.published
    result = skills.execute("ExchangeContainer", "Production", '{"container": 2}')
    assert result.accepted and fake.published[-1][0].endswith("/cmd/klt_exchange_command")
    disabled = dataclasses.replace(config.skills["Produce"], disabled=True)
    gw.configure(dataclasses.replace(config, skills={**config.skills, "Produce": disabled}))
    assert "disabled" in skills.execute("Produce").message


def test_execute_skill_applies_the_unit_mode(config):
    gw, fake = _gateway(config, "STOPPED", auto_start=False)
    result = SkillExecutor(gw, auto_start_wait=0.2).execute("Produce", "Maintenance")
    assert result.accepted and result.state == "EXECUTE", result.message
    assert fake.unit_mode == 2 and fake.published[0][0].endswith("/cmd/unit_mode_command")
    assert "already in EXECUTE" in SkillExecutor(gw).execute("Produce", "Maintenance").message
    assert "stop the line first" in SkillExecutor(gw).execute("Produce", "Production").message


def test_maintain_stops_the_line_and_confirms_the_finger_change(config, opcua_config):
    reset = opcua_config.endpoints["GripperMaintenanceReset"]
    assert (reset.protocol, reset.name) == ("mqtt", "gripper_maintenance_reset"), "robot RB01: MQTT/UNS"
    assert reset.form.topic == "vf/plant01/final-assembly/line01/rb01/cmd/gripper_maintenance_reset"
    assert config.skills["Maintain"].modes == ["Maintenance"]
    gw, fake = _gateway(config, "EXECUTE", auto_start=False)
    skills = SkillExecutor(gw)
    result = skills.execute("Maintain")
    assert result.accepted and result.state == "STOPPED" and fake.unit_mode == 2, result.message
    assert [p[0].rsplit("/", 1)[-1] for p in fake.published] == ["packml_command", "unit_mode_command"]
    assert fake.published[0][1]["v"] == packml.COMMANDS["Stop"]
    result = skills.execute("Maintain", "Maintenance", '{"gripper_maintenance_reset": true}')
    assert result.accepted and "gripper_maintenance_reset sent to GripperMaintenanceReset" in result.message
    assert fake.published[-1][0] == reset.form.topic and fake.published[-1][1]["v"] is True
    count = len(fake.published)
    assert skills.execute("Maintain", "", {"gripper_maintenance_reset": False}).accepted
    assert len(fake.published) == count, "false = nothing to confirm"
    assert "unknown unit mode" in skills.set_unit_mode("Turbo").message
    back = skills.set_unit_mode("Production")
    assert back.accepted and fake.unit_mode == 1 and back.state == "STOPPED"
    running, _ = _gateway(config, "EXECUTE")
    assert "stop the line first" in SkillExecutor(running).set_unit_mode("Maintenance").message


def test_operation_variables(config):
    args = input_arguments(json.dumps([{"value": {"modelType": "Property", "idShort": "Command",
                                                  "valueType": "xs:string", "value": "Start"}}]).encode())
    assert args == {"Command": "Start"}
    out = output_variables(Result(True, "ok", "EXECUTE"), with_state=True)
    assert [v["value"]["idShort"] for v in out] == ["Accepted", "State", "Message"]
    gw, _ = _gateway(config, "EXECUTE")
    assert health(gw)["endpoints"]["PackMLCommand"]["affordance"] == "packml_command"
