"""Template library: IDTA templates (vendored JSON) and Virtual Factory custom templates (YAML DSL).

Custom template DSL (aas/templates/custom/*.yaml):

    name: EnergyConsumption            # template idShort
    version: "1"                        # administration version/revision
    revision: "0"
    description: {en: ..., de: ...}
    elements:
      - idShort: RatedPower
        modelType: Property             # default Property
        valueType: xs:double
        cardinality: One                # One | ZeroToOne | ZeroToMany | OneToMany
        unit: W
        preferredName: {en: rated power, de: Bemessungsleistung}
        definition: {en: ..., de: ...}
        supplementalSemanticIds: [...]  # optional, e.g. equivalent ECLASS IRDIs
        elements: [...]                 # children of collections / entities / lists
        inputs: [...]                   # Operation: input / output / inoutput variables (element specs)
        outputs: [...]

Each element gets the semantic id <ID_BASE>/cd/<name>/<idShort>/<version>/<revision> (unless given) and an
IEC 61360 concept description, so custom templates have the same structure and quality as IDTA templates.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from ..ids import ID_BASE
from .values import mlp_value

IEC61360 = "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIec61360/3/0"
DROPIN_USE = "https://admin-shell.io/smt-dropin/smt-dropin-use/1/0"
# SMT drop-ins: empty collections whose content is defined by an element of another template
DROPINS = {"https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation":
           ("ContactInformations-1.0", "ContactInformation")}
DATA_TYPES = {"xs:double": "REAL_MEASURE", "xs:float": "REAL_MEASURE", "xs:decimal": "REAL_MEASURE",
              "xs:int": "INTEGER_COUNT", "xs:integer": "INTEGER_COUNT", "xs:long": "INTEGER_COUNT",
              "xs:unsignedInt": "INTEGER_COUNT", "xs:boolean": "BOOLEAN", "xs:dateTime": "TIMESTAMP",
              "xs:date": "DATE", "xs:duration": "STRING", "xs:anyURI": "IRI", "xs:string": "STRING"}
OPERATION_VARIABLES = {"inputs": "inputVariables", "outputs": "outputVariables",
                       "inoutputs": "inoutputVariables"}


class TemplateLibrary:
    def __init__(self, root: Path):
        self.templates: dict[str, dict] = {}
        self.concept_descriptions: dict[str, dict] = {}
        for f in sorted((root / "idta").glob("*-*.json")):
            if f.name != "manifest.json":
                self.templates[f.stem] = json.loads(f.read_text())
        for cd in json.loads((root / "idta" / "concept_descriptions.json").read_text()):
            self.concept_descriptions[cd["id"]] = cd
        for f in sorted((root / "custom").glob("*.yaml")):
            template, cds = compile_custom_template(yaml.safe_load(f.read_text()))
            self.templates[f"{template['idShort']}-{_ver(template)}"] = template
            self.concept_descriptions.update({cd["id"]: cd for cd in cds})
        for template in self.templates.values():
            self._expand_dropins(template.get("submodelElements", []))

    def _expand_dropins(self, elements: list) -> None:
        for el in elements:
            children = el.get("value") if isinstance(el.get("value"), list) else None
            sem = (el.get("semanticId") or {}).get("keys", [{}])[0].get("value")
            sup = [k["value"] for r in el.get("supplementalSemanticIds") or [] for k in r["keys"]]
            if el.get("modelType") == "SubmodelElementCollection" and not children and DROPIN_USE in sup \
                    and sem in DROPINS:
                donor_template, donor_id = DROPINS[sem]
                donor = next(e for e in self.templates[donor_template]["submodelElements"]
                             if e.get("idShort") == donor_id)
                el["value"] = copy.deepcopy(donor.get("value", []))
            for child in (children or []) + (el.get("statements") or []):
                self._expand_dropins([child])

    def get(self, name: str) -> dict:
        if name not in self.templates:
            raise KeyError(f"unknown template '{name}' (known: {', '.join(sorted(self.templates))})")
        return copy.deepcopy(self.templates[name])

    def concept_descriptions_for(self, element_tree) -> list[dict]:
        ids: set[str] = set()
        _collect_semantic_ids(element_tree, ids)
        return [self.concept_descriptions[i] for i in sorted(ids) if i in self.concept_descriptions]


def compile_custom_template(spec: dict) -> tuple[dict, list[dict]]:
    name, ver, rev = spec["name"], str(spec["version"]), str(spec.get("revision", "0"))
    cds: list[dict] = []
    template = {
        "modelType": "Submodel", "kind": "Template", "idShort": name,
        "id": f"{ID_BASE}/smt/{name}/{ver}/{rev}",
        "semanticId": _ref(spec.get("semanticId") or f"{ID_BASE}/smt/{name}/{ver}/{rev}/Submodel"),
        "administration": {"version": ver, "revision": rev},
        "description": mlp_value(spec["description"]),
        "submodelElements": [_element(e, name, ver, rev, cds) for e in spec["elements"]],
    }
    if spec.get("displayName"):
        template["displayName"] = mlp_value(spec["displayName"])
    return template, cds


def _element(e: dict, tname: str, ver: str, rev: str, cds: list[dict]) -> dict:
    mt = e.get("modelType", "Property")
    sem = e.get("semanticId") or f"{ID_BASE}/cd/{tname}/{e.get('conceptName', e['idShort'])}/{ver}/{rev}"
    el = {"modelType": mt, "idShort": e["idShort"], "semanticId": _ref(sem),
          "description": mlp_value(e.get("definition") or e.get("preferredName") or e["idShort"]),
          "qualifiers": [{"type": "SMT/Cardinality", "valueType": "xs:string", "kind": "TemplateQualifier",
                          "value": e.get("cardinality", "One")}]}
    if e.get("supplementalSemanticIds"):
        el["supplementalSemanticIds"] = [_ref(s) for s in e["supplementalSemanticIds"]]
    _type_fields(el, e, mt, tname, ver, rev, cds)
    if not e.get("semanticId") and sem not in {c["id"] for c in cds}:
        cds.append(_concept_description(sem, e, mt))
    return el


def _type_fields(el: dict, e: dict, mt: str, tname: str, ver: str, rev: str, cds: list[dict]) -> None:
    children = [_element(c, tname, ver, rev, cds) for c in e.get("elements", [])]
    if mt == "Property":
        el["valueType"] = e.get("valueType", "xs:string")
        if "value" in e:
            el["value"] = str(e["value"])
    elif mt == "Range":
        el["valueType"] = e.get("valueType", "xs:double")
    elif mt == "File":
        el["contentType"] = e.get("contentType", "application/octet-stream")
    elif mt == "SubmodelElementCollection":
        el["value"] = children
    elif mt == "SubmodelElementList":
        el["typeValueListElement"] = e.get("typeValueListElement", "SubmodelElementCollection")
        el["orderRelevant"] = e.get("orderRelevant", True)
        if e.get("valueTypeListElement"):
            el["valueTypeListElement"] = e["valueTypeListElement"]
        if e.get("semanticIdListElement"):
            el["semanticIdListElement"] = _ref(e["semanticIdListElement"])
        elif children:
            el["semanticIdListElement"] = children[0]["semanticId"]
        el["value"] = children
    elif mt == "Entity":
        el["entityType"] = e.get("entityType", "SelfManagedEntity")
        el["statements"] = children
    elif mt == "Operation":
        for key, field in OPERATION_VARIABLES.items():
            variables = [_element(c, tname, ver, rev, cds) for c in e.get(key, [])]
            for var in variables:
                var.pop("qualifiers")  # operation variables are always present
            if variables:
                el[field] = [{"value": var} for var in variables]


def _concept_description(cd_id: str, e: dict, mt: str) -> dict:
    content = {"modelType": "DataSpecificationIec61360",
               "preferredName": mlp_value(e.get("preferredName") or {"en": e["idShort"]}),
               "definition": mlp_value(e.get("definition") or e.get("preferredName") or e["idShort"])}
    short = e.get("conceptName", e["idShort"])
    if len(short) <= 18:  # IEC 61360 ShortNameTypeIEC61360
        content["shortName"] = mlp_value({"en": short})
    if mt == "Property":
        content["dataType"] = DATA_TYPES.get(e.get("valueType", "xs:string"), "STRING")
        if e.get("valueType") in ("xs:int", "xs:integer", "xs:long") and e.get("unit"):
            content["dataType"] = "INTEGER_MEASURE"
        if e.get("valueType") in ("xs:double", "xs:float") and not e.get("unit"):
            content["dataType"] = "REAL_COUNT"
    elif mt == "MultiLanguageProperty":
        content["dataType"] = "STRING_TRANSLATABLE"
    elif mt == "File":
        content["dataType"] = "FILE"
    if e.get("unit"):
        content["unit"] = e["unit"]
    if e.get("valueFormat"):
        content["valueFormat"] = e["valueFormat"]
    return {"modelType": "ConceptDescription", "id": cd_id, "idShort": e["idShort"],
            "embeddedDataSpecifications": [{"dataSpecification": _ref(IEC61360),
                                            "dataSpecificationContent": content}]}


def _ref(value: str) -> dict:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}


def _ver(sm: dict) -> str:
    adm = sm.get("administration") or {}
    return f"{adm.get('version', '1')}.{adm.get('revision', '0')}"


def _collect_semantic_ids(node, ids: set[str]) -> None:
    if isinstance(node, dict):
        for key in ("semanticId", "semanticIdListElement"):
            if node.get(key):
                ids.update(k["value"] for k in node[key].get("keys", []))
        for v in node.values():
            _collect_semantic_ids(v, ids)
    elif isinstance(node, list):
        for v in node:
            _collect_semantic_ids(v, ids)
