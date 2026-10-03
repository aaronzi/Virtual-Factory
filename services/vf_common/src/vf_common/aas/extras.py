"""Extra elements: fully specified elements that are not part of a template ("+Name" in the asset data)."""

from __future__ import annotations

from ..ids import ID_BASE
from .values import convert_property_value, mlp_value

EXTRA_META = ("semanticId", "description", "value", "unit", "conceptName", "_noValue")
CONCEPT_TYPES = ("Property", "MultiLanguageProperty", "Range")


def extra_element(id_short: str, spec: dict, concepts: dict | None = None) -> dict:
    """A fully specified element that is not part of the template (e.g. technical properties).

    Properties without an explicit semanticId get a generated concept description (unit, definition from the
    description): `{value, valueType, unit, description, conceptName?}`; the unit never goes into the text."""
    el = {k: v for k, v in spec.items() if k not in EXTRA_META}
    el.setdefault("modelType", "Property")
    if id_short:
        el["idShort"] = id_short
    semantic_id = spec.get("semanticId")
    if not semantic_id and id_short and concepts is not None and el["modelType"] in CONCEPT_TYPES:
        name = spec.get("conceptName", id_short)
        semantic_id = f"{ID_BASE}/cd/property/{name}"
        concepts[semantic_id] = {"idShort": name, "valueType": el.get("valueType", "xs:string"),
                                 "unit": spec.get("unit"), "description": spec.get("description"),
                                 "modelType": el["modelType"]}
    if semantic_id:
        el["semanticId"] = {"type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": semantic_id}]}
    if spec.get("description"):
        el["description"] = mlp_value(spec["description"])
    if el["modelType"] == "Property":
        el.setdefault("valueType", "xs:string")
        if not spec.get("_noValue"):
            el["value"] = convert_property_value(el["valueType"], spec.get("value"))
    elif el["modelType"] == "MultiLanguageProperty":
        el["value"] = mlp_value(spec.get("value", ""))
    elif "value" in spec:
        el["value"] = spec["value"]
    return el
