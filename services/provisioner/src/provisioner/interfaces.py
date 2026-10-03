"""Generates Asset Interfaces Description (MQTT, UNS topics) and Mapping Configuration values from the
device's FMI model description, so AAS interface descriptions can never diverge from the simulation."""

from __future__ import annotations

import json

from vf_common import ids

from .fmi import FmiVariable, ModelDescription
from .security_profile import mqtt_scheme

AID = "AssetInterfacesDescription"
INTERFACE = "InterfaceMQTT"
WOT = "https://www.w3.org/2019/wot/"
JSON_SCHEMA = WOT + "json-schema#"
RDF_TYPE = "https://www.w3.org/1999/02/22-rdf-syntax-ns#type"
AID_KEY = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/key"
_CORR = {"type": "string", "title": "correlation id (echoed in the acknowledgement)"}
_SOURCE = {"type": "string", "title": "sender name"}


def aid_values(tag: str, instance: str, md: ModelDescription, uns: dict, title: str,
               field_types: dict[str, str] | None = None) -> dict:
    """MQTT interface (UNS) of every device; controllers with a communication module also get the OPC UA
    interface of their server (interfaces_opcua, ADR-0024). field_types: FMI types of all devices' variables
    ("QS01.r" -> "Float64", event fields)."""
    from .interfaces_opcua import opcua_interface
    values = _mqtt_values(tag, instance, md, uns, title)
    opcua = opcua_interface(tag, instance, md, uns, field_types or {})
    if opcua:
        values["InterfaceTemplateForOPCUA"] = [opcua]
    return values


def _mqtt_values(tag: str, instance: str, md: ModelDescription, uns: dict, title: str) -> dict:
    device = instance.lower()
    root = uns["topic_root"]
    scheme, _ = mqtt_scheme()  # nosec, or basic in the secure profile (ADR-0027)
    sec = [{"ref": f"sm:{tag}/{AID}#{INTERFACE}.EndpointMetadata.securityDefinitions.{scheme}"}]
    props = []
    for var in md.by_causality("output"):
        topic = uns["telemetry"]["topic"].format(root=root, device=device, variable=var.name)
        props.append(_property(var, topic, uns["telemetry"], sec, uns["payload"], "subscribe"))
    actions = {}
    for name in uns["commands"].get("writable", {}).get(instance, []):
        topics = [uns["commands"][k].format(root=root, device=device, variable=name)
                  for k in ("topic", "ack_topic")]
        actions["+" + name] = _action(tag, md.variable(name), topics, uns["commands"], uns["payload"])
    events = {}
    for ev in uns.get("events", {}).get("definitions", []):
        if ev["device"] == instance:
            topic = uns["events"]["topic"].format(root=root, device=device, event=ev["event"])
            events["+" + ev["event"]] = _event(tag, ev, topic, uns["events"])
    interface = {
        "_idShort": INTERFACE, "title": title,
        "EndpointMetadata": {"base": uns["broker"]["base"], "contentType": uns["payload"]["content_type"],
                             "security": sec, "securityDefinitions": dict([mqtt_scheme()])},
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


def _action(tag: str, var: FmiVariable, topics: list[str], cfg: dict, payload: dict) -> dict:
    """WoT action affordance (extra element: 'actions' is an open collection in the AID template).

    Publishing {"v": <value>, "corr": <id>, "source": <name>} to the command topic sets the FMI input (form
    `forms`, op invokeaction). The controller answers on the acknowledgement topic (form `ackForms`, op
    queryaction, TD 1.1) with {"corr", "accepted", "reason", "v", "ts"} - described as the action's output
    schema (ADR-0020)."""
    title = var.description or var.name
    value = {"type": var.json_type, "title": title}
    inputs = [("Value", payload["value_key"], value), ("CorrelationId", "corr", _CORR),
              ("Source", "source", _SOURCE)]
    outputs = [("CorrelationId", "corr", _CORR),
               ("Accepted", "accepted", {"type": "boolean", "title": "true if the command was applied"}),
               ("Reason", "reason", {"type": "string", "title": "rejection reason (empty when accepted)"}),
               ("Value", payload["value_key"], {**value, "title": "applied value (null when rejected)"}),
               ("Timestamp", payload["timestamp_key"], {"type": "string", "title": "ISO 8601 timestamp"})]
    ack = {**cfg, "retain": False}
    return _affordance("ActionAffordance", title, [
        _prop("synchronous", "false", WOT + "td#isSynchronous", "xs:boolean"),
        _schema("input", WOT + "td#hasInputSchema", inputs),
        _schema("output", WOT + "td#hasOutputSchema", outputs),
        _form(tag, "forms", "invokeaction", topics[0], cfg, "publish"),
        _form(tag, "ackForms", "queryaction", topics[1], ack, "subscribe")])


def _event(tag: str, ev: dict, topic: str, cfg: dict) -> dict:
    """WoT event affordance ('events' is open as well): a flat JSON object with event, ts, session, seq and
    the fields of the event definition in godot/config/uns.json."""
    title = f"{ev['description']} (fields: {', '.join(ev.get('fields', {}))})"
    form = _form(tag, "forms", "subscribeevent", topic, cfg, "subscribe")
    return _affordance("EventAffordance", title, [form])


def _affordance(kind: str, title: str, elements: list[dict]) -> dict:
    return {"modelType": "SubmodelElementCollection", "semanticId": WOT + "td#" + kind,
            "description": {"en": title}, "value": [_prop("title", title, WOT + "td#title"), *elements]}


def _form(tag: str, id_short: str, op: str, topic: str, cfg: dict, packet: str) -> dict:
    """WoT form (MQTT binding). AID 1.1 holds one form per affordance (`forms`); a second form of an action
    (`ackForms`) carries the same semanticId td#hasForm and is told apart by `op`."""
    scheme = {"type": "ModelReference", "keys": [
        {"type": "Submodel", "value": ids.submodel_id(tag, AID, "1")},
        {"type": "SubmodelElementCollection", "value": INTERFACE},
        {"type": "SubmodelElementCollection", "value": "EndpointMetadata"},
        {"type": "SubmodelElementCollection", "value": "securityDefinitions"},
        {"type": "SubmodelElementCollection", "value": mqtt_scheme()[0]}]}
    return {"modelType": "SubmodelElementCollection", "idShort": id_short,
            "semanticId": _ext(WOT + "td#hasForm"),
            "value": [_prop("op", op, WOT + "hypermedia#hasOperationType"),
                      _prop("href", "/" + topic, WOT + "hypermedia#hasTarget"),
                      _prop("contentType", "application/json", WOT + "hypermedia#forContentType"),
                      {"modelType": "SubmodelElementList", "idShort": "security",
                       "typeValueListElement": "ReferenceElement",
                       "semanticId": _ext(WOT + "td#hasSecurityConfiguration"),
                       "value": [{"modelType": "ReferenceElement", "value": scheme}]},
                      _prop("mqv_retain", str(cfg["retain"]).lower(), WOT + "mqtt#hasRetainFlag"),
                      _prop("mqv_qos", str(cfg["qos"]), WOT + "mqtt#hasQoSFlag"),
                      _prop("mqv_controlPacket", packet, WOT + "mqtt#ControlPacket")]}


def _schema(id_short: str, semantic_id: str, entries: list[tuple[str, str, dict]]) -> dict:
    """JSON object schema (TD DataSchema) with one entry per payload key, structured like the nested
    `properties` of the AID property affordances (idShort = name, `key` = JSON key)."""
    props = [{"modelType": "SubmodelElementCollection", "idShort": name,
              "semanticId": _ext(JSON_SCHEMA + "propertyName"),
              "value": [_prop("key", key, AID_KEY), _prop("type", spec["type"], RDF_TYPE),
                        _prop("title", spec["title"], WOT + "td#title")]}
             for name, key, spec in entries]
    return {"modelType": "SubmodelElementCollection", "idShort": id_short, "semanticId": _ext(semantic_id),
            "value": [_prop("type", "object", RDF_TYPE),
                      {"modelType": "SubmodelElementCollection", "idShort": "properties",
                       "semanticId": _ext(JSON_SCHEMA + "properties"), "value": props}]}


def _prop(id_short: str, value: str, semantic_id: str, value_type: str = "xs:string") -> dict:
    return {"modelType": "Property", "idShort": id_short, "valueType": value_type, "value": value,
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
