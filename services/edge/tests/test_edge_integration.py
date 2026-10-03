"""OPC UA path against the running stack (`uv run pytest -m integration`, ADR-0024): browse the PLC01 server,
read the PackML state, run a LineControl operation BaSyx -> ops gateway -> OPC UA -> PLC, and see PLC01 on the
UNS (published by the edge). The checks that need live values skip when the simulation (PLC CPU) is not
linked to plc-comm."""

from __future__ import annotations

import asyncio
import json
import queue
import time

import httpx
import paho.mqtt.client as paho
import pytest
from asyncua import Client, ua

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.opcua_plc import NS_INDEX
from vf_common.uns import Uns

pytestmark = pytest.mark.integration
ENDPOINT = "opc.tcp://localhost:4840/vf/plc01"
NAMESPACE = "urn:virtual-factory:plant01:line01:plc01"


def _read(*identifiers: str) -> list[ua.DataValue]:
    async def read():
        async with Client(ENDPOINT, timeout=5) as client:
            ns = await client.get_namespace_index(NAMESPACE)
            return [await client.get_node(ua.NodeId(i, ns)).read_data_value(raise_on_bad_status=False)
                    for i in identifiers]
    try:
        return asyncio.run(read())
    except (OSError, asyncio.TimeoutError) as exc:
        pytest.skip(f"PLC01 OPC UA server not reachable ({exc})")


@pytest.fixture(scope="module")
def cpu_linked() -> bool:
    return bool(_read("PLC01.Diagnostics.CpuConnected")[0].Value.Value)


def test_browse_packml_structure():
    async def browse():
        async with Client(ENDPOINT, timeout=5) as client:
            assert await client.get_namespace_index(NAMESPACE) == NS_INDEX
            plc = await client.nodes.objects.get_child(f"{NS_INDEX}:PLC01")
            names = {(await n.read_browse_name()).Name for n in await plc.get_children()}
            path = ["0:Objects"] + [f"{NS_INDEX}:{name}" for name in ("PLC01", "Status", "StateCurrent")]
            state = await client.nodes.root.get_child(path)
            return names, state.nodeid.Identifier
    try:
        names, state_id = asyncio.run(browse())
    except (OSError, asyncio.TimeoutError) as exc:
        pytest.skip(f"PLC01 OPC UA server not reachable ({exc})")
    assert {"Status", "Admin", "BaseStateMachine", "SetUnitMode", "Program", "Commands",
            "Diagnostics"} <= names
    assert state_id == "PLC01.Status.StateCurrent"


def test_read_packml_state(cpu_linked):
    state, name = _read("PLC01.Status.StateCurrent", "PLC01.BaseStateMachine.CurrentState")
    if not cpu_linked:
        assert state.StatusCode.name == "BadNoCommunication"
        pytest.skip("simulation not linked to plc-comm")
    assert state.StatusCode.is_good() and 1 <= state.Value.Value <= 17 and name.Value.Value


def test_command_round_trip_basyx_ops_gateway_opcua(cpu_linked):
    if not cpu_linked:
        pytest.skip("simulation not linked to plc-comm")
    health = httpx.get("http://localhost:8095/health", timeout=5).json()
    assert health["endpoints"]["PackMLCommand"]["protocol"] == "opcua"
    aas = BasyxClient("http://localhost:8091")
    line_control = ids.submodel_id("LINE01", "LineControl", "1")
    start = time.perf_counter()
    held = aas.invoke(line_control, "ExecutePackMLCommand", {"Command": "Hold"})
    hold_s = time.perf_counter() - start
    try:
        assert held["Accepted"] == "true" and held["State"] == "HELD", held
        assert _read("PLC01.Status.StateCurrent")[0].Value.Value == 11
    finally:
        resumed = aas.invoke(line_control, "ExecutePackMLCommand", {"Command": "Unhold"})
    assert resumed["Accepted"] == "true" and resumed["State"] == "EXECUTE", resumed
    print(f"Hold via BaSyx -> ops gateway -> OPC UA -> PLC -> state HELD observed: {hold_s * 1000:.0f} ms")


def test_uns_receives_plc01_from_the_edge(cpu_linked):
    if not cpu_linked:
        pytest.skip("simulation not linked to plc-comm")
    uns = Uns.load()
    topic = uns.telemetry("PLC01", "packml_state")
    received: queue.Queue = queue.Queue()
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="vf-test-edge")
    client.on_message = lambda _c, _u, msg: received.put(json.loads(msg.payload))
    client.connect("localhost", 1883)
    client.subscribe(topic)
    client.loop_start()
    seen = []
    try:  # retained value first; the edge publishes changes within its 100 ms interval: let it catch up
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            seen.append(received.get(timeout=max(deadline - time.monotonic(), 0.01)))
            if seen[-1]["v"] == _read("PLC01.Status.StateCurrent")[0].Value.Value:
                break
    except queue.Empty:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
    current = _read("PLC01.Status.StateCurrent")[0].Value.Value
    assert seen and seen[-1]["v"] == current and seen[-1]["ts"].endswith("Z"), (seen, current)
