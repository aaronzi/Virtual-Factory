"""PackML rules and the command round trip against a simulated controller (no broker needed)."""

from __future__ import annotations

import json
import queue

from ops_gateway import packml
from ops_gateway.gateway import LineGateway
from ops_gateway.server import input_arguments, output_variables
from vf_common.mqtt import Message
from vf_common.uns import Uns

STATE = {name: i for i, name in enumerate(packml.STATES)}


class FakeController:
    """Stands in for broker + Godot gateway: acknowledges commands and walks through PackML states."""

    def __init__(self, uns: Uns, state: str, auto_start: bool = True, accept: bool = True):
        self.uns, self.auto_start, self.accept = uns, auto_start, accept
        self.messages: queue.Queue[Message] = queue.Queue()
        self.published = []
        self._state(state)

    def subscribe(self, topic, qos=1):
        pass

    def get(self, timeout=None):
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def publish(self, topic, payload, qos=1, retain=False):
        self.published.append((topic, payload))
        variable = topic.rsplit("/", 1)[-1]
        ack = {"corr": payload["corr"], "accepted": self.accept, "v": payload["v"]}
        if not self.accept:
            ack["reason"] = "not writable"
        self.messages.put(Message(self.uns.ack("PLC01", variable), json.dumps(ack).encode()))
        if self.accept and variable == "packml_command":
            for state in self._walk(payload["v"]):
                self._state(state)

    def _walk(self, command: int) -> list[str]:
        name = next(k for k, v in packml.COMMANDS.items() if v == command)
        target = packml.TARGET[name]
        return [target, "STARTING", "EXECUTE"] if target == "IDLE" and self.auto_start else [target]

    def _state(self, name: str) -> None:
        payload = json.dumps({"v": STATE[name], "ts": "t"}).encode()
        self.messages.put(Message(self.uns.telemetry("PLC01", "packml_state"), payload))


def _gateway(state: str, **kw) -> tuple[LineGateway, FakeController]:
    uns = Uns.load()
    fake = FakeController(uns, state, **kw)
    gw = LineGateway(fake, uns, ack_timeout=1.0, state_timeout=1.0)
    gw.start()
    assert gw._wait_for(lambda: gw.state == STATE[state], 1.0)
    return gw, fake


def test_rules():
    assert packml.check("Start", "IDLE") is None
    assert "not allowed in state STOPPED (allowed: Abort, Reset)" in packml.check("Start", "STOPPED")
    assert "unknown command" in packml.check("Jump", "IDLE")


def test_hold_round_trip():
    gw, fake = _gateway("EXECUTE")
    result = gw.packml_command("Hold")
    assert result.accepted and result.state == "HELD"
    assert fake.published[0][0].endswith("/plc01/cmd/packml_command") and fake.published[0][1]["v"] == 4


def test_reset_with_auto_start_sees_transient_idle():
    gw, _ = _gateway("STOPPED")
    result = gw.packml_command("Reset")
    assert result.accepted, result.message


def test_rejections():
    gw, fake = _gateway("STOPPED")
    assert not gw.packml_command("Hold").accepted and not fake.published
    gw2, _ = _gateway("EXECUTE", accept=False)
    assert gw2.set_auto_exchange(False).message == "not writable"
    assert not gw2.exchange_container(3).accepted


def test_operation_variables():
    args = input_arguments(json.dumps([{"value": {"modelType": "Property", "idShort": "Command",
                                                  "valueType": "xs:string", "value": "Start"}}]).encode())
    assert args == {"Command": "Start"}
    from ops_gateway.gateway import Result
    out = output_variables(Result(True, "ok", "EXECUTE"), with_state=True)
    assert [v["value"]["idShort"] for v in out] == ["Accepted", "State", "Message"]
