"""OPC UA address space of a controller's communication module (ADR-0024), derived from its FMI model
description and the UNS registry (`opcua.servers.<instance>` in godot/config/uns.json). Shared by the server
(plc_comm) and the AID generator (provisioner), so the AAS forms always match the server.

    Objects/<instance>                      PackML base object (structure after OPC 30050, no type nodeset)
        TagID, PackMLVersion                properties
        Status.*, Admin.*                   FMI variables mapped by `packml_tags` (e.g. Status.StateCurrent)
        BaseStateMachine                    CurrentState + methods Reset ... Clear (write the PackML command)
        SetUnitMode(UnitMode)               writes the unit mode command (`packml_commands`)
        Program/Inputs|Outputs|Parameters   all other FMI variables, named as in the FMI model (tag table)
        Commands/<variable>(Value)          one method per writable variable of the UNS registry
        Diagnostics                         CpuConnected, SessionId, ImageUpdates (communication module)
    Types/EventTypes/BaseEventType/<Name>EventType   one per UNS event of the instance (Session, Seq, fields)

NodeIds are strings in the server namespace: `ns=2;s=<instance>.<path>`, e.g. `PLC01.Status.StateCurrent`.
AID forms use `href = ?id=nsu=<namespace uri>;s=<identifier>` (independent of the namespace index) and
`uav_browsePath = /0:Objects/2:<instance>/2:...`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .packml import COMMANDS

NS_INDEX = 2  # the server registers its namespace first (0 = OPC UA, 1 = server application)
PACKML_VERSION = "OPC 30050 (PackML) 1.01 - structure only, no type nodeset"
FOLDERS = {"input": "Inputs", "output": "Outputs", "parameter": "Parameters"}
DIAGNOSTICS = {"CpuConnected": "Boolean", "SessionId": "String", "ImageUpdates": "UInt64"}


class FmiVar(Protocol):
    name: str
    type: str
    causality: str
    description: str


@dataclass(frozen=True)
class Node:
    path: tuple[str, ...]      # browse names below Objects, e.g. ("PLC01", "Status", "StateCurrent")
    kind: str                  # object | variable | method
    variable: str = ""         # variables: FMI value source; methods: FMI variable written
    type: str = ""             # FMI type of the value / method argument
    value: object = None       # methods: fixed value written (PackML command methods); constants
    argument: str = ""         # methods: name of the single input argument ("" = none)
    description: str = ""

    @property
    def identifier(self) -> str:
        return ".".join(self.path)

    @property
    def browse_path(self) -> str:
        return "/0:Objects/" + "/".join(f"{NS_INDEX}:{name}" for name in self.path)


@dataclass(frozen=True)
class EventType:
    event: str                 # UNS event name, e.g. part_inspected
    name: str                  # browse name, e.g. PartInspectedEventType
    fields: dict[str, str]     # event field -> FMI type (plus Session: String, Seq: Int64)
    description: str = ""

    @property
    def identifier(self) -> str:
        return self.name

    @property
    def browse_path(self) -> str:
        return f"/0:Types/0:EventTypes/0:BaseEventType/{NS_INDEX}:{self.name}"


@dataclass
class AddressSpace:
    instance: str
    namespace: str
    endpoint: str
    nodes: list[Node] = field(default_factory=list)
    events: list[EventType] = field(default_factory=list)

    def value_node(self, variable: str) -> Node:
        """The node that shows an FMI variable's value."""
        return next(n for n in self.nodes if n.kind == "variable" and n.variable == variable)

    def command_node(self, variable: str) -> Node:
        """The generic method that writes a writable FMI variable (Commands/<variable>)."""
        return next(n for n in self.nodes if n.kind == "method" and n.path[1] == "Commands"
                    and n.variable == variable)

    def event_type(self, event: str) -> EventType:
        return next(e for e in self.events if e.event == event)

    def href(self, identifier: str) -> str:
        return href(self.namespace, identifier)


def href(namespace: str, identifier: str) -> str:
    return f"?id=nsu={namespace};s={identifier}"


def parse_href(value: str) -> tuple[str, str]:
    """`?id=nsu=<uri>;s=<identifier>` -> (namespace uri, identifier)."""
    node_id = value.split("?id=", 1)[-1]
    if not node_id.startswith("nsu=") or ";s=" not in node_id:
        raise ValueError(f"unsupported OPC UA href {value!r} (expected ?id=nsu=<uri>;s=<identifier>)")
    namespace, identifier = node_id[4:].split(";s=", 1)
    return namespace, identifier


def servers(uns: dict) -> dict[str, dict]:
    """Controllers served over OPC UA ({} if the OPC UA path is disabled in the registry)."""
    section = uns.get("opcua") or {}
    return section.get("servers", {}) if section.get("enabled", False) else {}


def address_space(instance: str, variables: list[FmiVar], uns: dict,
                  field_types: dict[str, str] | None = None) -> AddressSpace:
    """field_types: FMI type of event fields outside the controller ("QS01.r" -> "Float64")."""
    cfg = uns["opcua"]["servers"][instance]
    space = AddressSpace(instance, cfg["namespace"], cfg["endpoint"])
    root = (instance,)
    space.nodes.append(Node(root, "object", description=f"{instance} (PackML base object)"))
    space.nodes += [Node(root + ("TagID",), "variable", type="String", value=instance),
                    Node(root + ("PackMLVersion",), "variable", type="String", value=PACKML_VERSION)]
    space.nodes += _packml_nodes(root, variables, cfg)
    space.nodes += _program_nodes(root, variables, set(cfg.get("packml_tags", {}).values()))
    writable = uns.get("commands", {}).get("writable", {}).get(instance, [])
    space.nodes.append(Node(root + ("Commands",), "object", description="One method per writable variable"))
    space.nodes += [_method(root + ("Commands", name), _var(variables, name), "Value") for name in writable]
    space.nodes.append(Node(root + ("Diagnostics",), "object", description="Communication module"))
    space.nodes += [Node(root + ("Diagnostics", n), "variable", type=t) for n, t in DIAGNOSTICS.items()]
    space.events = _event_types(instance, variables, uns, field_types or {})
    return space


def _packml_nodes(root: tuple, variables: list[FmiVar], cfg: dict) -> list[Node]:
    tags = cfg.get("packml_tags", {})
    nodes = [Node(root + (folder,), "object") for folder in sorted({t.split(".")[0] for t in tags})]
    for tag, name in tags.items():
        var = _var(variables, name)
        nodes.append(Node(root + tuple(tag.split(".")), "variable", name, var.type,
                          description=var.description))
    commands = cfg.get("packml_commands", {})
    if "BaseStateMachine" in commands:
        var = _var(variables, commands["BaseStateMachine"])
        machine = root + ("BaseStateMachine",)
        nodes += [Node(machine, "object", description="PackML base state machine"),
                  Node(machine + ("CurrentState",), "variable", "packml_state:name", "String")]
        nodes += [Node(machine + (cmd,), "method", var.name, var.type, value=number,
                       description=f"PackML command {cmd} ({var.name} = {number})")
                  for cmd, number in COMMANDS.items()]
    if "SetUnitMode" in commands:
        nodes.append(_method(root + ("SetUnitMode",), _var(variables, commands["SetUnitMode"]), "UnitMode"))
    return nodes


def _program_nodes(root: tuple, variables: list[FmiVar], mapped: set[str]) -> list[Node]:
    program = root + ("Program",)
    nodes = [Node(program, "object", description="Tag table of the PLC program (FMI variables)")]
    for causality, folder in FOLDERS.items():
        nodes.append(Node(program + (folder,), "object"))
        nodes += [Node(program + (folder, v.name), "variable", v.name, v.type, description=v.description)
                  for v in variables if v.causality == causality and v.name not in mapped]
    return nodes


def _method(path: tuple, var: FmiVar, argument: str) -> Node:
    return Node(path, "method", var.name, var.type, argument=argument, description=var.description)


def _event_types(instance: str, variables: list[FmiVar], uns: dict, field_types: dict) -> list[EventType]:
    own = {f"{instance}.{v.name}": v.type for v in variables}
    out = []
    for ev in uns.get("events", {}).get("definitions", []):
        if ev["device"] != instance:
            continue
        fields = {"Session": "String", "Seq": "Int64"}
        for name, path in ev.get("fields", {}).items():
            fields[name] = own.get(path) or field_types.get(path) or "String"
        type_name = "".join(part.capitalize() for part in ev["event"].split("_")) + "EventType"
        out.append(EventType(ev["event"], type_name, fields, ev.get("description", "")))
    return out


def _var(variables: list[FmiVar], name: str) -> FmiVar:
    found = next((v for v in variables if v.name == name), None)
    if found is None:
        raise KeyError(f"no FMI variable '{name}' (referenced by opcua.servers in godot/config/uns.json)")
    return found
