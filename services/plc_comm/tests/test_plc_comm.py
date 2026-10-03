"""Communication module: address space engineered from the FMI model + registry, OPC UA server fed by a
scripted CPU over the backplane (no Godot, no Docker)."""

from __future__ import annotations

import asyncio
import socket

import pytest
from asyncua import Client, ua

from plc_comm.module import comm_module, engineer, load_uns
from plc_comm.testing import FakeCpu
from vf_common.opcua_plc import NS_INDEX, parse_href


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def space():
    return engineer("PLC01", load_uns())


def test_address_space_follows_packml_and_the_fmi_model(space):
    state = space.value_node("packml_state")
    assert state.identifier == "PLC01.Status.StateCurrent"
    assert state.browse_path == f"/0:Objects/{NS_INDEX}:PLC01/{NS_INDEX}:Status/{NS_INDEX}:StateCurrent"
    assert space.value_node("parts_nok").identifier == "PLC01.Admin.ProdDefectiveCount"
    assert space.value_node("cv_run").identifier == "PLC01.Program.Outputs.cv_run"
    assert space.value_node("lb01_signal").identifier == "PLC01.Program.Inputs.lb01_signal"
    assert space.value_node("exchange_delay").identifier == "PLC01.Program.Parameters.exchange_delay"
    command = space.command_node("packml_command")
    assert (command.identifier, command.argument, command.type) == ("PLC01.Commands.packml_command", "Value",
                                                                   "Int32")
    machine = [n for n in space.nodes if n.kind == "method" and n.path[1] == "BaseStateMachine"]
    assert [n.path[-1] for n in machine][:3] == ["Reset", "Start", "Stop"] and machine[1].value == 2
    inspected = space.event_type("part_inspected")
    assert inspected.name == "PartInspectedEventType"
    assert inspected.fields["hue"] == "Float64" and inspected.fields["serial"] == "String"
    assert parse_href(space.href(state.identifier)) == (space.namespace, "PLC01.Status.StateCurrent")
    assert not [n for n in space.nodes if n.kind == "variable" and n.variable == "time"]


def test_server_round_trip(space):
    asyncio.run(_round_trip(space))


async def _round_trip(space):
    port, bp = free_port(), free_port()
    url = f"opc.tcp://127.0.0.1:{port}/vf/plc01"
    async with comm_module(space, url, "127.0.0.1", bp) as module:
        async with Client(url) as client:
            ns = await client.get_namespace_index(space.namespace)
            node = lambda ident: client.get_node(ua.NodeId(ident, ns))  # noqa: E731
            hold = ua.Variant(4, ua.VariantType.Int32)
            with pytest.raises(ua.UaStatusCodeError, match="BadNotConnected"):
                await node("PLC01").call_method(node("PLC01.Commands.packml_command"), hold)
            cpu = FakeCpu(state="EXECUTE")
            await cpu.connect("127.0.0.1", bp)
            await asyncio.sleep(0.2)
            assert await node("PLC01.Status.StateCurrent").read_value() == 6
            assert await node("PLC01.BaseStateMachine.CurrentState").read_value() == "EXECUTE"
            assert await node("PLC01.Program.Outputs.cv_run").read_value() is True
            assert await node("PLC01.Diagnostics.CpuConnected").read_value() is True
            assert await node("PLC01.Diagnostics.SessionId").read_value() == "S-test"
            await node("PLC01").call_method(node("PLC01.Commands.packml_command"), hold)
            await asyncio.sleep(0.1)
            assert cpu.writes == [("packml_command", 4)]
            assert await node("PLC01.Status.StateCurrent").read_value() == 11
            await node("PLC01.BaseStateMachine").call_method(node("PLC01.BaseStateMachine.Unhold"))
            await node("PLC01").call_method(node("PLC01.SetUnitMode"), ua.Variant(2, ua.VariantType.Int32))
            assert cpu.writes[1:] == [("packml_command", 5), ("unit_mode_command", 2)]
            await _events(client, ns, cpu)
            await cpu.close()
            await asyncio.sleep(0.2)
            value = await node("PLC01.Status.StateCurrent").read_data_value(raise_on_bad_status=False)
            assert value.StatusCode.name == "BadNoCommunication"
            assert module.backplane.stats["writes"] == 3


async def _events(client: Client, ns: int, cpu: FakeCpu) -> None:
    received = []

    class Handler:
        def event_notification(self, event):
            received.append(event.get_event_props_as_fields_dict())

    sub = await client.create_subscription(50, Handler())
    type_node = client.get_node(ua.NodeId("PartSortedEventType", ns))
    await sub.subscribe_events(client.get_node(ua.NodeId("PLC01", ns)), [type_node])
    await cpu.event("part_sorted", serial="S7", container=2, slot=3)
    await asyncio.sleep(0.3)
    assert len(received) == 1
    fields = {k: v.Value for k, v in received[0].items()}
    assert (fields["serial"], fields["container"], fields["slot"], fields["Seq"]) == ("S7", 2, 3, 1)
    assert fields["Session"] == "S-test" and fields["SourceName"] == "PLC01"
    await sub.delete()
