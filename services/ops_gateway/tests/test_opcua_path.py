"""Ops gateway over OPC UA (ADR-0024): the Control Component endpoints of PLC01 resolve to the OPC UA
interface of its AID; commands are method calls on the real communication module (plc_comm) fed by a
scripted CPU, the PackML state and unit mode are monitored items. No broker, no Godot."""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest

from ops_gateway.control import resolve
from ops_gateway.gateway import LineGateway
from ops_gateway.opcua_link import OpcUaLink
from ops_gateway.skills import SkillExecutor
from plc_comm.module import comm_module, engineer, load_uns
from plc_comm.testing import FakeCpu
from provisioner.build import build
from vf_common import ids
from vf_common.aid import InMemoryAas


class _NoMqtt:
    def subscribe(self, topic, qos=1):
        # the only MQTT endpoint is the robot's GripperMaintenanceReset (RB01 has no OPC UA server)
        if "/rb01/cmd-resp/" not in topic:
            raise AssertionError(f"OPC UA endpoints must not subscribe MQTT topics ({topic})")

    def unsubscribe(self, topic):
        pass


class Plant:
    """Communication module + scripted CPU in their own event loop thread."""

    def __init__(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.backplane = s.getsockname()[1]
        self.loop = asyncio.new_event_loop()
        self.cpu = FakeCpu(state="EXECUTE")
        self._stop = asyncio.Event()
        self._ready = threading.Event()
        threading.Thread(target=self.loop.run_until_complete, args=(self._run(),), daemon=True).start()
        assert self._ready.wait(10)

    async def _run(self):
        url = f"opc.tcp://127.0.0.1:{self.port}/vf/plc01"
        async with comm_module(engineer("PLC01", load_uns()), url, "127.0.0.1", self.backplane):
            await self.cpu.connect("127.0.0.1", self.backplane)
            self._ready.set()
            await self._stop.wait()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(5)

    def stop(self):
        self.loop.call_soon_threadsafe(self._stop.set)


@pytest.fixture(scope="module")
def plant():
    plant = Plant()
    yield plant
    plant.stop()


@pytest.fixture(scope="module")
def gateway(plant):
    config = resolve(InMemoryAas(build().environment), ids.submodel_id("LINE01", "LineControl", "1"))
    holder = []
    link = OpcUaLink(lambda name, value: holder[0].on_value(name, value),
                     mapping={"opc.tcp://localhost:4840": f"opc.tcp://127.0.0.1:{plant.port}"})
    link.start()
    gw = LineGateway(_NoMqtt(), state_timeout=3.0, opcua=link)
    holder.append(gw)
    gw.configure(config)
    assert gw.wait_state(lambda s: s == "EXECUTE", 10), "state observed over OPC UA"
    return gw


def test_packml_command_is_a_method_call(plant, gateway):
    result = gateway.packml_command("Hold")
    assert result.accepted and result.state == "HELD", result.message
    assert plant.cpu.writes[-1] == ("packml_command", 4)
    assert gateway.packml_command("Unhold").state == "EXECUTE"


def test_skills_and_unit_mode_over_opcua(plant, gateway):
    skills = SkillExecutor(gateway, auto_start_wait=0.3)
    result = skills.execute("ExchangeContainer", "Production", {"container": 1})
    assert result.accepted and plant.cpu.writes[-1] == ("klt_exchange_command", 1), result.message
    assert "stop the line first" in skills.execute("Produce", "Maintenance").message
    assert gateway.packml_command("Stop").accepted
    result = skills.execute("Produce", "Maintenance")
    assert result.accepted and "Reset -> Start" in result.message, result.message
    assert gateway.values["UnitMode"] == 2 and ("unit_mode_command", 2) in plant.cpu.writes


def test_cpu_not_linked_is_reported(plant, gateway):
    plant.run(plant.cpu.close())
    result = gateway.set_auto_exchange(False)
    assert not result.accepted and "BadNotConnected" in result.message, result.message
