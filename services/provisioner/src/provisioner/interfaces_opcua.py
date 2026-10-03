"""Generates the OPC UA interface of the Asset Interfaces Description (AID 1.1, InterfaceTemplateForOPCUA) for
controllers with a communication module (`opcua.servers` in godot/config/uns.json, ADR-0024). The forms come
from the same address space model the server is built from (vf_common.opcua_plc), so they cannot diverge.

    properties  every FMI output: href ?id=nsu=<ns>;s=<node>, uav_browsePath (readproperty/observeproperty)
    actions     every writable variable: method Commands/<variable>(Value), op invokeaction, synchronous
                (the result is the status code of the call: Good, BadNotConnected, BadNotExecutable, ...)
    events      every UNS event of the controller: the OPC UA event type (op subscribeevent); the controller
                object (parent of the methods) is the EventNotifier
"""

from __future__ import annotations

from pathlib import Path

from vf_common import ids
from vf_common.opcua_plc import AddressSpace, Node, address_space, servers

from .fmi import JSON_TYPES, ModelDescription, read_model_description
from .interfaces import AID, WOT, _affordance, _ext, _prop, _schema
from .security_profile import opcua_definitions

INTERFACE = "InterfaceOPCUA"
CONTENT_TYPE = "application/octet-stream"  # OPC UA binary encoding (UA TCP)
SECURITY = ("opcua_channel_sc", "opcua_authentication_sc")
BROWSE_PATH = "http://opcfoundation.org/UA/WoT-Binding/browsePath"


def device_models(repo: Path, specs: list[dict]) -> dict[str, ModelDescription]:
    """FMI model description per instance name of all device asset specs."""
    out = {}
    for spec in specs:
        device = spec.get("device")
        if device:
            md = read_model_description(repo / device["modelDescription"])
            out[device.get("instance", spec["tag"])] = md
    return out


def field_types(models: dict[str, ModelDescription]) -> dict[str, str]:
    """"INSTANCE.variable" -> FMI type, for the event fields of other devices."""
    return {f"{name}.{v.name}": v.type for name, md in models.items() for v in md.variables}


def opcua_interface(tag: str, instance: str, md: ModelDescription, uns: dict,
                    field_types: dict[str, str]) -> dict | None:
    """Values of one InterfaceTemplateForOPCUA, or None if the instance has no OPC UA server."""
    if instance not in servers(uns):
        return None
    space = address_space(instance, list(md.variables), uns, field_types)
    sec = [{"ref": f"sm:{tag}/{AID}#{INTERFACE}.EndpointMetadata.securityDefinitions.{name}"}
           for name in SECURITY]
    props = [_property(space, md.variable(v.name), sec) for v in md.by_causality("output")]
    writable = uns.get("commands", {}).get("writable", {}).get(instance, [])
    actions = {"+" + name: _action(tag, space, space.command_node(name)) for name in writable}
    events = {"+" + e.event: _event(tag, space, e) for e in space.events}
    return {
        "_idShort": INTERFACE, "title": f"{tag} OPC UA server (communication module of the controller)",
        "EndpointMetadata": {
            "base": space.endpoint, "contentType": CONTENT_TYPE, "security": sec,
            # None/Anonymous, or Basic256Sha256 SignAndEncrypt + UserName in the secure profile (ADR-0027)
            "securityDefinitions": opcua_definitions(),
        },
        "InteractionMetadata": {"properties": {"property_name": props},
                                **({"actions": actions} if actions else {}),
                                **({"events": events} if events else {})},
    }


def _property(space: AddressSpace, var, sec: list) -> dict:
    node = space.value_node(var.name)
    spec = {"type": var.json_type, "title": var.description or var.name}
    if var.unit:
        spec["unit"] = var.unit
    return {"_idShort": var.name, **spec, "observable": True,
            "forms": {"href": space.href(node.identifier), "security": sec,
                      "uav_browsePath": node.browse_path}}


def _action(tag: str, space: AddressSpace, node: Node) -> dict:
    title = f"{node.description or node.variable} (OPC UA method {node.path[-2]}.{node.path[-1]})"
    value = {"type": JSON_TYPES[node.type], "title": node.description or node.variable}
    inputs = [("Value", node.argument, value)]
    return _affordance("ActionAffordance", title, [
        _prop("synchronous", "true", WOT + "td#isSynchronous", "xs:boolean"),
        _schema("input", WOT + "td#hasInputSchema", inputs),
        _form(tag, space, "invokeaction", node.identifier, node.browse_path)])


def _event(tag: str, space: AddressSpace, event_type) -> dict:
    fields = ", ".join(event_type.fields)
    title = f"{event_type.description} (OPC UA event type {event_type.name}, fields: {fields})"
    return _affordance("EventAffordance", title, [
        _form(tag, space, "subscribeevent", event_type.identifier, event_type.browse_path)])


def _form(tag: str, space: AddressSpace, op: str, identifier: str, browse_path: str) -> dict:
    """WoT form (OPC UA binding of AID 1.1: href + uav_browsePath), op as in the MQTT forms (ADR-0020)."""
    refs = [{"modelType": "ReferenceElement", "value": {"type": "ModelReference", "keys": [
        {"type": "Submodel", "value": ids.submodel_id(tag, AID, "1")},
        {"type": "SubmodelElementCollection", "value": INTERFACE},
        {"type": "SubmodelElementCollection", "value": "EndpointMetadata"},
        {"type": "SubmodelElementCollection", "value": "securityDefinitions"},
        {"type": "SubmodelElementCollection", "value": name}]}} for name in SECURITY]
    return {"modelType": "SubmodelElementCollection", "idShort": "forms",
            "semanticId": _ext(WOT + "td#hasForm"),
            "value": [_prop("op", op, WOT + "hypermedia#hasOperationType"),
                      _prop("href", space.href(identifier), WOT + "hypermedia#hasTarget"),
                      {"modelType": "SubmodelElementList", "idShort": "security",
                       "typeValueListElement": "ReferenceElement",
                       "semanticId": _ext(WOT + "td#hasSecurityConfiguration"), "value": refs},
                      _prop("uav_browsePath", browse_path, BROWSE_PATH)]}

