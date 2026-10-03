"""Instantiation of submodel templates (AAS V3.0 JSON) from plain data.

Data is a nested dict keyed by idShort (see docs/interfaces/aas-model.md, "Asset data format"):

    Property                 scalar                       ManufacturerName: {en: ..., de: ...} (MLP)
    SubmodelElementCollection dict                        File: "path" or {value, contentType}
    SubmodelElementList      list of item data            Range: {min, max, valueType?}
    placeholder X__00__ / repeated ZeroToMany element: list -> X01, X02, ... (or "_idShort" per item)
    ReferenceElement         {"ref": "<resolver key>"}    Entity: {entityType, globalAssetId, specificAssetIds, statements}
    RelationshipElement      {"first": "<key>", "second": "<key>"}
    Capability               {} (only "_idShort"/"_description")
    Blob                     {"contentType": ..., "value": str | bytes | JSON object}
    extra element            "+Name": {modelType, valueType, value, semanticId, description, ...}
    any element              "_idShort" / "_description" / "_semanticId" override the template values

Unfilled optional elements (ZeroToOne/ZeroToMany) are removed. Unfilled mandatory leaves are kept with an
empty value and reported in `InstantiationResult.missing`. Template qualifiers (SMT/*) are removed.
"""

from __future__ import annotations

import base64
import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .values import convert_property_value, file_value, mlp_value

PLACEHOLDER = re.compile(r"__\d\d__|\{\d\d\}")
OPTIONAL = {"ZeroToOne", "ZeroToMany"}
MULTIPLE = {"ZeroToMany", "OneToMany"}
CONTAINERS = {"SubmodelElementCollection", "SubmodelElementList", "Entity"}
RefResolver = Callable[[str], dict]


@dataclass
class InstantiationResult:
    submodel: dict
    missing: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def instantiate(template: dict, data: dict, submodel_id: str, resolver: RefResolver,
                id_short: str | None = None, template_id: str | None = None) -> InstantiationResult:
    """Creates a submodel instance from `template` filled with `data`."""
    sm = copy.deepcopy(template)
    result = InstantiationResult(sm)
    ctx = _Ctx(resolver, result)
    sm["id"] = submodel_id
    sm["idShort"] = id_short or sm.get("idShort")
    sm["kind"] = "Instance"
    admin = dict(sm.get("administration") or {})
    admin["templateId"] = template_id or template["id"]
    sm["administration"] = {k: v for k, v in admin.items() if k in ("version", "revision", "templateId")}
    sm.pop("qualifiers", None)
    sm["submodelElements"] = ctx.fill_elements(sm.get("submodelElements", []), data or {}, sm["idShort"])
    return result


class _Ctx:
    def __init__(self, resolver: RefResolver, result: InstantiationResult):
        self.resolver = resolver
        self.result = result

    # -- element lists ---------------------------------------------------------------------------

    def fill_elements(self, templates: list[dict], data: dict, path: str) -> list[dict]:
        out: list[dict] = []
        used: set[str] = set()
        for tmpl in templates:
            name = tmpl.get("idShort", "")
            key = self._data_key(name, data)
            if key is not None:
                used.add(key)
                out += self.fill_named(tmpl, data[key], f"{path}.{key}")
            elif _cardinality(tmpl) not in OPTIONAL and not PLACEHOLDER.search(name):
                out.append(self.fill_one(tmpl, {} if tmpl["modelType"] in CONTAINERS else None, f"{path}.{name}"))
        for key, value in data.items():
            if key.startswith("+"):
                out.append(_extra_element(key[1:], value))
            elif key not in used and not key.startswith("_"):
                self.result.unknown.append(f"{path}.{key}")
        return out

    def fill_named(self, tmpl: dict, value: Any, path: str) -> list[dict]:
        name = tmpl.get("idShort", "")
        repeat = PLACEHOLDER.search(name) or (_cardinality(tmpl) in MULTIPLE and isinstance(value, list)
                                              and tmpl["modelType"] != "SubmodelElementList")
        if not repeat:
            return [self.fill_one(tmpl, value, path)]
        base = PLACEHOLDER.sub("", name)
        items = value if isinstance(value, list) else [value]
        out = []
        for i, item in enumerate(items, start=1):
            el = self.fill_one(tmpl, item, f"{path}[{i}]")
            el["idShort"] = (item.get("_idShort") if isinstance(item, dict) else None) or f"{base}{i:02d}"
            out.append(el)
        return out

    # -- single element --------------------------------------------------------------------------

    def fill_one(self, tmpl: dict, value: Any, path: str) -> dict:
        el = copy.deepcopy(tmpl)
        el.pop("qualifiers", None)
        if isinstance(value, dict) and "_idShort" in value:
            el["idShort"] = value["_idShort"]
        if isinstance(value, dict) and "_description" in value:
            el["description"] = mlp_value(value["_description"])
        if isinstance(value, dict) and "_semanticId" in value:
            el["semanticId"] = {"type": "ExternalReference",
                                "keys": [{"type": "GlobalReference", "value": value["_semanticId"]}]}
        filler = getattr(self, "_fill_" + el["modelType"], None)
        if filler is None:
            return el
        filler(el, value, path)
        return el

    def _fill_Property(self, el: dict, value: Any, path: str) -> None:
        if isinstance(value, dict):  # {value, valueType, semanticId, _idShort, ...} for repeated properties
            if value.get("valueType"):
                el["valueType"] = value["valueType"]
            if value.get("semanticId"):
                el["semanticId"] = {"type": "ExternalReference",
                                    "keys": [{"type": "GlobalReference", "value": value["semanticId"]}]}
            value = value.get("value")
        if value is None:
            el["value"] = ""
            self.result.missing.append(path)
        else:
            el["value"] = convert_property_value(el.get("valueType", "xs:string"), value)

    def _fill_MultiLanguageProperty(self, el: dict, value: Any, path: str) -> None:
        if value is None:
            el.pop("value", None)
            self.result.missing.append(path)
        else:
            el["value"] = mlp_value(value)

    def _fill_File(self, el: dict, value: Any, path: str) -> None:
        if value is None:
            el.pop("value", None)
            self.result.missing.append(path)
        else:
            el.update(file_value(value))

    def _fill_Blob(self, el: dict, value: Any, path: str) -> None:
        """{contentType, value}: value (str/bytes, or JSON-serialisable for application/json) is base64-encoded."""
        if not value:
            el.pop("value", None)
            return
        content = value.get("value")
        el["contentType"] = value.get("contentType", "application/octet-stream")
        raw = content if isinstance(content, bytes) else (
            json.dumps(content) if el["contentType"] == "application/json" and not isinstance(content, str)
            else str(content)).encode()
        el["value"] = base64.b64encode(raw).decode()

    def _fill_Range(self, el: dict, value: Any, path: str) -> None:
        value = value or {}
        if value.get("valueType"):
            el["valueType"] = value["valueType"]
        vt = el.get("valueType", "xs:double")
        for bound in ("min", "max"):
            if value.get(bound) is not None:
                el[bound] = convert_property_value(vt, value[bound])
            else:
                el.pop(bound, None)

    def _fill_ReferenceElement(self, el: dict, value: Any, path: str) -> None:
        if not value:
            el.pop("value", None)
            self.result.missing.append(path)
        else:
            el["value"] = self.resolver(value["ref"] if isinstance(value, dict) else value)

    def _fill_RelationshipElement(self, el: dict, value: Any, path: str) -> None:
        value = value or {}
        for end in ("first", "second"):
            if value.get(end):
                el[end] = self.resolver(value[end])
            else:
                self.result.missing.append(f"{path}.{end}")

    def _fill_SubmodelElementCollection(self, el: dict, value: Any, path: str) -> None:
        el["value"] = self.fill_elements(el.get("value", []), value or {}, path)

    def _fill_Entity(self, el: dict, value: Any, path: str) -> None:
        value = value or {}
        for key in ("entityType", "globalAssetId"):
            if key in value:
                el[key] = value[key]
        if value.get("specificAssetIds"):
            el["specificAssetIds"] = [{"name": k, "value": str(v)} for k, v in value["specificAssetIds"].items()]
        if el.get("entityType") == "CoManagedEntity":
            el.pop("globalAssetId", None)
            el.pop("specificAssetIds", None)
        el["statements"] = self.fill_elements(el.get("statements", []), value.get("statements", {}), path)

    def _fill_SubmodelElementList(self, el: dict, value: Any, path: str) -> None:
        item_tmpl = (el.get("value") or [None])[0]
        items = value if isinstance(value, list) else []
        if item_tmpl is None:
            el["value"] = [_extra_element("", v) for v in items]
        else:
            el["value"] = [self._list_item(item_tmpl, v, f"{path}[{i}]") for i, v in enumerate(items)]
        _fix_list_value_type(el)

    def _list_item(self, item_tmpl: dict, value: Any, path: str) -> dict:
        item = self.fill_one(item_tmpl, value, path)
        item.pop("idShort", None)  # AASd-120: list elements have no idShort
        return item

    def _data_key(self, name: str, data: dict) -> str | None:
        if name in data:
            return name
        base = PLACEHOLDER.sub("", name)
        return base if base != name and base in data else None


# includes upstream spelling variants found in IDTA templates (e.g. "ZerotoMany", "Three", "TwoToMany")
CARDINALITY_ALIASES = {"1": "One", "0..1": "ZeroToOne", "0..*": "ZeroToMany", "1..*": "OneToMany",
                       "one": "One", "zerotoone": "ZeroToOne", "zerotomany": "ZeroToMany",
                       "onetomany": "OneToMany", "three": "One", "twotomany": "OneToMany"}


def _cardinality(el: dict) -> str:
    """SMT cardinality; templates use SMT/Cardinality, Cardinality, Multiplicity (older) qualifiers."""
    for q in el.get("qualifiers") or []:
        qtype = q.get("type", "")
        if qtype.endswith("Cardinality") or qtype == "Multiplicity":
            value = q.get("value", "One")
            return CARDINALITY_ALIASES.get(value, CARDINALITY_ALIASES.get(value.lower(), value))
    return "One"


def _fix_list_value_type(el: dict) -> None:
    """Upstream template fix: SML of Property needs valueTypeListElement (AASd-109)."""
    if el.get("typeValueListElement") in ("Property", "Range") and not el.get("valueTypeListElement"):
        items = el.get("value") or []
        el["valueTypeListElement"] = items[0].get("valueType", "xs:string") if items else "xs:string"


def _extra_element(id_short: str, spec: dict) -> dict:
    """A fully specified element that is not part of the template (e.g. technical properties)."""
    el = {k: v for k, v in spec.items() if k not in ("semanticId", "description", "value")}
    el.setdefault("modelType", "Property")
    if id_short:
        el["idShort"] = id_short
    if spec.get("semanticId"):
        el["semanticId"] = {"type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": spec["semanticId"]}]}
    if spec.get("description"):
        el["description"] = mlp_value(spec["description"])
    if el["modelType"] == "Property":
        el.setdefault("valueType", "xs:string")
        el["value"] = convert_property_value(el["valueType"], spec.get("value"))
    elif el["modelType"] == "MultiLanguageProperty":
        el["value"] = mlp_value(spec.get("value", ""))
    elif "value" in spec:
        el["value"] = spec["value"]
    return el
