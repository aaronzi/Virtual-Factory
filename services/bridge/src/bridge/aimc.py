"""Interprets Asset Interfaces Mapping Configuration (IDTA 02027 v2.0) + Asset Interfaces Description (v1.1)
submodels: which MQTT topic and JSON key feed which submodel element, with which transformation. Nothing
device-specific is hard-coded - adding a device means adding its AAS."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from .transform import Transformation, TransformationError

AIMC_SEMANTIC_ID = "https://admin-shell.io/idta/AssetInterfacesMappingConfiguration/2/0/Submodel"
AID_SEMANTIC_ID = "https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel"
INTEGER_TYPES = {"xs:int", "xs:integer", "xs:long", "xs:short", "xs:unsignedInt", "xs:unsignedLong",
                 "xs:unsignedShort"}


@dataclass(frozen=True)
class Mapping:
    source_id: str
    topic: str
    value_key: str
    sink_submodel: str
    sink_path: str
    transformation: Transformation | None = None
    sink_type: str | None = None  # valueType of the sink Property

    def convert(self, value):
        """Transforms and converts a JSON value to the sink's value type; None if it cannot be mapped."""
        value = self.transform(value)
        if value is None or self.sink_type is None:
            return value
        try:
            if self.sink_type in ("xs:double", "xs:float", "xs:decimal"):
                return float(value)
            if self.sink_type in INTEGER_TYPES:
                return int(value)
            if self.sink_type == "xs:boolean":
                return bool(value)
        except (TypeError, ValueError):
            return None
        return str(value)

    def transform(self, value):
        """Applies the AIMC transformation (Lua aimc_main) if there is one; None = do not write."""
        if self.transformation is None:
            return value
        return self.transformation({self.source_id: value})


def mappings(aimc: dict, submodels: dict[str, dict]) -> list[Mapping]:
    """All mappings of one AIMC submodel; `submodels` resolves the referenced AID and sink submodels by id."""
    out = []
    for config in _child(aimc["submodelElements"], "MappingConfigurations")["value"]:
        sinks = [_child(s["value"], "Sink")["value"]["keys"]
                 for s in _child(config["value"], "Sinks")["value"]]
        transformation = _transformation(config["value"])
        for source in _child(config["value"], "Sources")["value"]:
            keys = _child(source["value"], "Source")["value"]["keys"]
            topic, value_key = _aid_endpoint(submodels[keys[0]["value"]], keys[1:])
            source_id = ((_child(source["value"], "SourceId", required=False) or {}).get("value")
                         or keys[-1]["value"])
            out += [Mapping(source_id, topic, value_key, sink[0]["value"],
                            ".".join(k["value"] for k in sink[1:]), transformation,
                            _sink_type(submodels.get(sink[0]["value"]), sink[1:]))
                    for sink in sinks]
    return out


def referenced_submodels(aimc: dict) -> set[str]:
    """Ids of the AID submodels the sources point into and of the submodels the sinks point into."""
    ids = set()
    for config in _child(aimc["submodelElements"], "MappingConfigurations")["value"]:
        for kind in ("Source", "Sink"):
            for item in _child(config["value"], kind + "s")["value"]:
                ids.add(_child(item["value"], kind)["value"]["keys"][0]["value"])
    return ids


def _sink_type(submodel: dict | None, keys: list[dict]) -> str | None:
    if submodel is None:
        return None
    element = {"value": submodel["submodelElements"]}
    try:
        for key in keys:
            element = _child(element["value"], key["value"])
    except (KeyError, IndexError, TypeError):
        return None
    return element.get("valueType")


def _aid_endpoint(aid: dict, keys: list[dict]) -> tuple[str, str]:
    """(topic, JSON value key) of the AID property affordance the keys point to."""
    element = {"value": aid["submodelElements"]}
    for key in keys:
        element = _child(element["value"], key["value"])
    forms = _child(element["value"], "forms")
    topic = _child(forms["value"], "href")["value"].lstrip("/")
    value_key = "v"
    nested = _child(element["value"], "properties", required=False)
    if nested:
        value_spec = _child(nested["value"], "Value", required=False)
        if value_spec:
            value_key = (_child(value_spec["value"], "key", required=False) or {}).get("value") or value_key
    return topic, value_key


def _transformation(elements: list[dict]) -> Transformation | None:
    """Lua transformation of a mapping (requires the Blob value: fetch the AIMC with extent=withBlobValue)."""
    blob = _child(elements, "Transformation", required=False)
    if not blob or not blob.get("value"):
        return None
    try:
        return Transformation(base64.b64decode(blob["value"]).decode())
    except (TransformationError, UnicodeDecodeError) as exc:
        raise KeyError(f"invalid transformation: {exc}") from exc


def _child(elements: list[dict], id_short: str, required: bool = True) -> dict | None:
    if id_short.isdigit():  # SubmodelElementList index
        return elements[int(id_short)]
    found = next((e for e in elements if e.get("idShort") == id_short), None)
    if found is None and required:
        raise KeyError(f"element '{id_short}' not found")
    return found
