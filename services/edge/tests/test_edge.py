"""Edge connector: AID pairing (OPC UA <-> MQTT affordances) and the bridge against the real communication
module with a scripted CPU (no broker: a recording MQTT stand-in)."""

from __future__ import annotations

import asyncio
import json
import socket

import pytest

from edge.config import resolve
from edge.connector import Connector
from plc_comm.module import comm_module, engineer, load_uns
from plc_comm.testing import FakeCpu
from provisioner.build import build
from vf_common.aid import InMemoryAas
from vf_common.mqtt import Message

ROOT = "vf/plant01/final-assembly/line01/plc01/"


class RecordingMqtt:
    def __init__(self):
        self.published: list[tuple[str, dict, int, bool]] = []
        self.subscribed: set[str] = set()

    def publish(self, topic, payload, qos=1, retain=False):
        self.published.append((topic, payload, qos, retain))

    def subscribe(self, topic, qos=1):
        self.subscribed.add(topic)

    def unsubscribe(self, topic):
        self.subscribed.discard(topic)

    def on(self, topic: str) -> list[dict]:
        return [p[1] for p in self.published if p[0] == topic]


@pytest.fixture(scope="module")
def links():
    return resolve(InMemoryAas(build().environment))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_aid_affordances_are_paired_by_name(links):
    assert len(links) == 1, "only PLC01 has an OPC UA interface"
    link = links[0]
    assert link.endpoint == "opc.tcp://localhost:4840/vf/plc01"
    state = next(r for r in link.properties if r.name == "packml_state")
    assert state.ua.form.topic.endswith(";s=PLC01.Status.StateCurrent") and state.uns.form.topic == ROOT + \
        "packml_state"
    assert {r.name for r in link.events} == {"part_inspected", "part_sorted"}
    assert {r.name for r in link.actions} == {"packml_command", "klt_exchange_command", "auto_exchange",
                                              "unit_mode_command"}
    command = next(r for r in link.actions if r.name == "packml_command")
    assert command.uns.form.topic == ROOT + "cmd/packml_command" and command.uns.ack.topic == \
        ROOT + "cmd-resp/packml_command"


def test_bridge_round_trip(links):
    asyncio.run(_bridge(links[0]))


async def _bridge(link):
    port, bp = free_port(), free_port()
    url = f"opc.tcp://127.0.0.1:{port}/vf/plc01"
    async with comm_module(engineer("PLC01", load_uns()), url, "127.0.0.1", bp):
        mqtt = RecordingMqtt()
        connector = Connector(link, mqtt, publishing_ms=20, mapping={"opc.tcp://localhost:4840":
                                                                     f"opc.tcp://127.0.0.1:{port}"})
        await connector.start()
        await asyncio.sleep(0.2)
        assert not mqtt.on(ROOT + "packml_state") and not mqtt.subscribed, "no CPU: nothing valid to publish"
        cpu = FakeCpu(state="EXECUTE")
        await cpu.connect("127.0.0.1", bp)
        await asyncio.sleep(0.3)
        state = mqtt.on(ROOT + "packml_state")[-1]
        assert state["v"] == 6 and state["ts"].endswith("Z")
        assert next(p for p in mqtt.published if p[0] == ROOT + "packml_state")[2:] == (0, True)
        assert ROOT + "cmd/packml_command" in mqtt.subscribed
        command = Message(ROOT + "cmd/packml_command", json.dumps({"v": 4, "corr": "c1"}).encode())
        assert await connector.handle_command(command)
        ack = mqtt.on(ROOT + "cmd-resp/packml_command")[-1]
        assert (ack["corr"], ack["accepted"], ack["reason"], ack["v"]) == ("c1", True, "", 4)
        await asyncio.sleep(0.2)
        assert mqtt.on(ROOT + "packml_state")[-1]["v"] == 11 and cpu.writes == [("packml_command", 4)]
        await connector.handle_command(Message(ROOT + "cmd/auto_exchange", b'{"v": "maybe", "corr": "c2"}'))
        assert not mqtt.on(ROOT + "cmd-resp/auto_exchange")[-1]["accepted"]
        await cpu.event("part_sorted", serial="S9", container=1, slot=4)
        await asyncio.sleep(0.2)
        event = mqtt.on(ROOT + "event/part_sorted")[-1]
        keys = ("event", "device", "session", "seq", "serial", "container", "slot")
        assert {k: event[k] for k in keys} == {"event": "part_sorted", "device": "PLC01", "session": "S-test",
                                               "seq": 1, "serial": "S9", "container": 1, "slot": 4}
        await cpu.close()
        await asyncio.sleep(0.3)
        assert not mqtt.subscribed, "command topics released without valid data"
        await connector.stop()
