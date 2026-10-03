"""Builds the controller's OPC UA address space (vf_common.opcua_plc) on an asyncua server and binds it to the
process image of the simulated CPU: values come from the backplane, method calls go back over it.

Value nodes carry the CPU's source timestamp (simulation time base). While no CPU is connected, every
process image node has the status BadNoCommunication and methods answer BadNotConnected."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from asyncua import Server, ua

from vf_common.opcua_plc import DIAGNOSTICS, NS_INDEX, AddressSpace, EventType, Node
from vf_common.packml import state_name

log = logging.getLogger("plc-comm")
VARIANTS = {"Float64": ua.VariantType.Double, "Int32": ua.VariantType.Int32, "UInt64": ua.VariantType.UInt64,
            "Boolean": ua.VariantType.Boolean, "String": ua.VariantType.String, "Int64": ua.VariantType.Int64}
# writer(variable, value) -> (accepted, reason); raises ConnectionError without CPU, TimeoutError
Writer = Callable[[str, object], Awaitable[tuple[bool, str]]]
DERIVED = ":name"  # CurrentState shows the state name of packml_state


def _variant(fmi_type: str, value) -> ua.Variant:
    vtype = VARIANTS[fmi_type]
    if value is None:
        value = ua.get_default_value(vtype)
    elif vtype == ua.VariantType.Double:
        value = float(value)
    elif vtype in (ua.VariantType.Int32, ua.VariantType.Int64, ua.VariantType.UInt64):
        value = int(value)
    return ua.Variant(value, vtype)


class PlcAddressSpace:
    def __init__(self, server: Server, space: AddressSpace, writer: Writer):
        self.server, self.space, self.writer = server, space, writer
        self.idx = NS_INDEX
        self.values: dict[str, list[tuple[ua.NodeId, str, bool]]] = {}  # variable -> [(node, type, derived)]
        self.events: dict[str, object] = {}                        # UNS event -> asyncua event generator
        self.diagnostics: dict[str, ua.NodeId] = {}
        self.updates = 0

    def node_id(self, identifier: str) -> ua.NodeId:
        return ua.NodeId(identifier, self.idx)

    async def build(self) -> None:
        self.idx = await self.server.register_namespace(self.space.namespace)
        if self.idx != NS_INDEX:
            log.warning("namespace index is %d, the AID browse paths assume %d", self.idx, NS_INDEX)
        nodes = {(): self.server.get_objects_node()}
        for spec in self.space.nodes:
            parent = nodes[spec.path[:-1]]
            nodes[spec.path] = await self._add(parent, spec)
        root = nodes[(self.space.instance,)]
        for event_type in self.space.events:
            type_node = await self._add_event_type(event_type)
            self.events[event_type.event] = await self.server.get_event_generator(type_node, root)
            # inverse of the GeneratesEvent reference the generator adds: clients find the notifier from the
            # event type (edge connector)
            await type_node.add_reference(root, ua.ObjectIds.GeneratesEvent, forward=False,
                                          bidirectional=False)
        await self.set_connected(False)

    async def _add(self, parent, spec: Node):
        node_id, name = self.node_id(spec.identifier), ua.QualifiedName(spec.path[-1], self.idx)
        if spec.kind == "object":
            node = await parent.add_object(node_id, name)
        elif spec.kind == "method":
            node = await parent.add_method(node_id, name, self._callback(spec), self._arguments(spec), [])
        else:
            node = await parent.add_variable(node_id, name, _variant(spec.type, spec.value))
            if spec.variable:
                variable, derived = spec.variable.removesuffix(DERIVED), spec.variable.endswith(DERIVED)
                self.values.setdefault(variable, []).append((node_id, spec.type, derived))
            if spec.path[-2] == "Diagnostics":
                self.diagnostics[spec.path[-1]] = node_id
        if spec.description:
            await node.write_attribute(ua.AttributeIds.Description,
                                       ua.DataValue(ua.Variant(ua.LocalizedText(spec.description, "en"))))
        return node

    def _arguments(self, spec: Node) -> list[ua.Argument]:
        if not spec.argument:
            return []
        return [ua.Argument(Name=spec.argument, DataType=ua.NodeId(VARIANTS[spec.type].value), ValueRank=-1,
                            Description=ua.LocalizedText(spec.description, "en"))]

    def _callback(self, spec: Node):
        async def call(_parent: ua.NodeId, *args: ua.Variant):
            if spec.argument and len(args) != 1:
                return ua.StatusCode(ua.StatusCodes.BadArgumentsMissing)
            value = args[0].Value if spec.argument else spec.value
            return await self._write(spec, value)
        return call

    async def _write(self, spec: Node, value) -> ua.StatusCode | list:
        try:
            accepted, reason = await self.writer(spec.variable, value)
        except ConnectionError:
            return ua.StatusCode(ua.StatusCodes.BadNotConnected)
        except TimeoutError:
            return ua.StatusCode(ua.StatusCodes.BadTimeout)
        if not accepted:
            log.info("%s(%r) rejected by the CPU: %s", spec.identifier, value, reason)
            bad = ua.StatusCodes.BadTypeMismatch if "expected" in reason else ua.StatusCodes.BadNotExecutable
            return ua.StatusCode(bad)
        return []

    async def _add_event_type(self, event_type: EventType):
        base = self.server.get_node(ua.ObjectIds.BaseEventType)
        node = await base.add_object_type(self.node_id(event_type.identifier),
                                          ua.QualifiedName(event_type.name, self.idx))
        for name, fmi_type in event_type.fields.items():
            await node.add_property(self.node_id(f"{event_type.identifier}.{name}"),
                                    ua.QualifiedName(name, self.idx), _variant(fmi_type, None))
        await node.write_attribute(ua.AttributeIds.Description,
                                   ua.DataValue(ua.Variant(ua.LocalizedText(event_type.description, "en"))))
        return node

    # -- process image ------------------------------------------------------------------------------

    async def update(self, values: dict, source_ts: datetime | None) -> None:
        now = datetime.now(timezone.utc)
        for variable, value in values.items():
            for node_id, fmi_type, derived in self.values.get(variable, []):
                shown = state_name(int(value)) if derived else value  # BaseStateMachine.CurrentState
                await self.server.write_attribute_value(node_id, ua.DataValue(
                    _variant(fmi_type, shown), SourceTimestamp=source_ts or now, ServerTimestamp=now))
        self.updates += 1
        await self._diagnostic("ImageUpdates", self.updates)

    async def set_connected(self, connected: bool, session: str = "") -> None:
        await self._diagnostic("CpuConnected", connected)
        await self._diagnostic("SessionId", session)
        if connected:
            return
        bad = ua.StatusCode(ua.StatusCodes.BadNoCommunication)
        for nodes in self.values.values():
            for node_id, _type, _derived in nodes:
                await self.server.write_attribute_value(node_id, ua.DataValue(StatusCode=bad))

    async def fire(self, event: str, payload: dict, source_ts: datetime | None) -> bool:
        generator = self.events.get(event)
        if generator is None:
            return False
        event_type = self.space.event_type(event)
        for name, fmi_type in event_type.fields.items():
            key = name.lower() if name in ("Session", "Seq") else name
            setattr(generator.event, name, _variant(fmi_type, payload.get(key)))
        generator.event.Severity = 100
        await generator.trigger(time_attr=source_ts, message=event_type.description)
        return True

    async def _diagnostic(self, name: str, value) -> None:
        node_id = self.diagnostics.get(name)
        if node_id is not None:
            await self.server.write_attribute_value(node_id, ua.DataValue(_variant(DIAGNOSTICS[name], value)))
