"""Generates Asset Interfaces Description (MQTT, UNS topics) and Mapping Configuration values from the
device's FMI model description, so AAS interface descriptions can never diverge from the simulation."""

from __future__ import annotations

import json

from vf_common import ids

from .fmi import FmiVariable, ModelDescription

AID = "AssetInterfacesDescription"
INTERFACE = "InterfaceMQTT"
NOSEC = f"{INTERFACE}.EndpointMetadata.securityDefinitions.nosec_sc"
WOT = "https://www.w3.org/2019/wot/"


def aid_values(tag: str, instance: str, md: ModelDescription, uns: dict, title: str) -> dict:
    device = instance.lower()
    root = uns["topic_root"]
    sec = [{"ref": f"sm:{tag}/{AID}#{NOSEC}"}]
    props = []
    for var in md.by_causality("output"):
        topic = uns["telemetry"]["topic"].format(root=root, device=device, variable=var.name)
        props.append(_property(var, topic, uns["telemetry"], sec, uns["payload"], "subscribe"))
    actions = {}
    for name in uns["commands"].get("writable", {}).get(instance, []):
        topic = uns["commands"]["topic"].format(root=root, device=device, variable=name)
        actions["+" + name] = _action(tag, md.variable(name), topic, uns["commands"])
    events = {}
    for ev in uns.get("events", {}).get("definitions", []):
        if ev["device"] == instance:
            topic = uns["events"]["topic"].format(root=root, device=device, event=ev["event"])
            events["+" + ev["event"]] = _event(tag, ev, topic, uns["events"])
    interface = {
        "_idShort": INTERFACE, "title": title,
        "EndpointMetadata": {"base": uns["broker"]["base"], "contentType": uns["payload"]["content_type"],
                             "security": sec, "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}}},
        "InteractionMetadata": {"properties": {"property_name": props},
                                **({"actions": actions} if actions else {}),
                                **({"events": events} if events else {})},
    }
    return {"InterfaceTemplateForMQTT": [interface]}


def _property(var: FmiVariable, topic: str, cfg: dict, sec: list, payload: dict, packet: str) -> dict:
    value_spec = {"type": var.json_type, "title": var.description or var.name}
    if var.unit:
        value_spec["unit"] = var.unit
    return {
        "_idShort": var.name, "type": "object", "title": var.description or var.name, "observable": True,
        "properties": {"property_name": [  # idShort >= 2 chars (AASd-002, V3.1+): JSON key goes into "key"
            {"_idShort": "Value", "key": payload["value_key"], **value_spec},
            {"_idShort": "Timestamp", "key": payload["timestamp_key"], "type": "string",
             "title": "ISO 8601 timestamp"}]},
        "forms": {"href": "/" + topic, "contentType": payload["content_type"], "security": sec,
                  "mqv_retain": str(cfg["retain"]).lower(), "mqv_qos": str(cfg["qos"]),
                  "mqv_controlPacket": packet},
    }


def _action(tag: str, var: FmiVariable, topic: str, cfg: dict) -> dict:
    """WoT action affordance (extra element: 'actions' is an open collection in the AID template).
    Publishing {"v": <value>} to the command topic sets the FMI input."""
    return _affordance(tag, "ActionAffordance", var.description or var.name, topic, cfg, "publish")


def _event(tag: str, ev: dict, topic: str, cfg: dict) -> dict:
    """WoT event affordance ('events' is open as well): a flat JSON object with event, ts, session, seq and
    the fields of the event definition in godot/config/uns.json."""
    title = f"{ev['description']} (fields: {', '.join(ev.get('fields', {}))})"
    return _affordance(tag, "EventAffordance", title, topic, cfg, "subscribe")


def _affordance(tag: str, kind: str, title: str, topic: str, cfg: dict, packet: str) -> dict:
    nosec = {"type": "ModelReference", "keys": [
        {"type": "Submodel", "value": ids.submodel_id(tag, AID, "1")},
        {"type": "SubmodelElementCollection", "value": INTERFACE},
        {"type": "SubmodelElementCollection", "value": "EndpointMetadata"},
        {"type": "SubmodelElementCollection", "value": "securityDefinitions"},
        {"type": "SubmodelElementCollection", "value": "nosec_sc"}]}
    forms = [_prop("href", "/" + topic, WOT + "hypermedia#hasTarget"),
             _prop("contentType", "application/json", WOT + "hypermedia#forContentType"),
             {"modelType": "SubmodelElementList", "idShort": "security",
              "typeValueListElement": "ReferenceElement",
              "semanticId": _ext(WOT + "td#hasSecurityConfiguration"),
              "value": [{"modelType": "ReferenceElement", "value": nosec}]},
             _prop("mqv_retain", str(cfg["retain"]).lower(), WOT + "mqtt#hasRetainFlag"),
             _prop("mqv_qos", str(cfg["qos"]), WOT + "mqtt#hasQoSFlag"),
             _prop("mqv_controlPacket", packet, WOT + "mqtt#ControlPacket")]
    return {"modelType": "SubmodelElementCollection", "semanticId": WOT + "td#" + kind,
            "description": {"en": title},
            "value": [_prop("title", title, WOT + "td#title"),
                      {"modelType": "SubmodelElementCollection", "idShort": "forms",
                       "semanticId": _ext(WOT + "td#hasForm"), "value": forms}]}


def _prop(id_short: str, value: str, semantic_id: str) -> dict:
    return {"modelType": "Property", "idShort": id_short, "valueType": "xs:string", "value": value,
            "semanticId": _ext(semantic_id)}


def _ext(value: str) -> dict:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}


def aimc_values(tag: str, mappings: list[tuple[str, str, dict | None]]) -> dict:
    """mappings: (FMI output, sink path 'Submodel#a.b', optional lookup table) -> one MappingConfiguration
    each."""
    configs = []
    for var, sink, lookup in mappings:
        cfg = {"Sources": [{"Source": {"ref": f"sm:{tag}/{AID}#{INTERFACE}"
                                              f".InteractionMetadata.properties.{var}"},
                            "SourceId": var}],
               "Sinks": [{"Sink": {"ref": f"sm:{tag}/{sink}"}, "SinkId": sink.split("#")[-1].split(".")[-1]}]}
        if lookup:
            cfg["Transformation"] = {"contentType": "text/x-lua", "value": lua_lookup(var, lookup)}
        configs.append(cfg)
    return {"MappingConfigurations": configs}


def lua_lookup(source_id: str, table: dict) -> str:
    """AIMC 2.0 transformation (Lua, entry point aimc_main(sources)) that maps a source value via a lookup
    table."""
    entries = ",\n".join(f'  [{json.dumps(str(k))}] = {json.dumps(v)}' for k, v in table.items())
    return (f"-- lookup {source_id} -> sink value (generated from the asset data: device.state.map)\n"
            f"local map = {{\n{entries}\n}}\n"
            "local function key(v)\n"
            "  if math.type(v) == \"float\" and v == math.floor(v) then return string.format(\"%d\", v) end\n"
            "  return tostring(v)\n"
            "end\n"
            "function aimc_main(sources)\n"
            f"  return map[key(sources[{json.dumps(source_id)}])]\n"
            "end\n")
