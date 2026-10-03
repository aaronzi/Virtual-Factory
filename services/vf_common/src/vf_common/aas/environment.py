"""Builds an AAS V3.0 environment (JSON) from asset definitions (aas/data/assets/*.yaml).

Asset definition (see docs/interfaces/aas-model.md):

    tag: AC01                      # asset tag -> ids (vf_common.ids)
    idShort: AC01_AssemblyCell
    kind: Instance | Type
    assetType: <IRI>
    displayName / description: {en, de}
    derivedFrom: <TAG of the type AAS>
    thumbnail: repo:docs/screenshots/assets/assembly_cell.png
    specificAssetIds: {serialNumber: ..., manufacturerPartId: ...}
    submodels:
      - template: Nameplate-3.0     # name in the TemplateLibrary
        idShort: Nameplate          # optional (default: template idShort)
        values: {...}               # see instantiate.py

String values may contain ${asset:TAG}, ${aas:TAG}, ${sm:TAG/IdShort} (replaced by identifiers).
ReferenceElements use {"ref": "aas:TAG" | "sm:TAG/IdShort" | "sm:TAG/IdShort#a.b.c" | "global:IRI"}.
TAG "SELF" stands for the asset being built (for shared files included by several assets).
File values / thumbnails starting with "repo:" are embedded as supplementary files; a thumbnail may also be
{path: <absolute URL>, contentType} (runtime AAS referring to an existing image).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .. import ids
from .instantiate import instantiate
from .templates import TemplateLibrary, concept_description
from .values import file_value, mlp_value

NUMERIC = {"xs:double", "xs:float", "xs:decimal", "xs:int", "xs:integer", "xs:long", "xs:short",
           "xs:unsignedInt", "xs:unsignedLong", "xs:unsignedShort"}
# units of template semantic ids without concept description (ECLASS IRDIs used by IDTA templates)
TEMPLATE_UNITS = {"0173-1#02-ABH960#002": "°", "0173-1#02-ABH961#002": "°"}
VAR = re.compile(r"\$\{(asset|aas|sm):([^}]+)\}")
SELF = re.compile(r"^SELF(?=$|/)")


@dataclass
class BuildReport:
    missing: dict[str, list[str]] = field(default_factory=dict)
    unknown: dict[str, list[str]] = field(default_factory=dict)


class EnvironmentBuilder:
    def __init__(self, library: TemplateLibrary):
        self.library = library
        self.shells: list[dict] = []
        self.submodels: list[dict] = []
        self.files: dict[str, str] = {}      # package path -> repo path
        self.shell_files: dict[str, set[str]] = {}   # aas id -> package paths
        self.report = BuildReport()
        self._sm_ids: dict[str, str] = {}    # "TAG/IdShort" -> submodel id
        self._pending: list[dict] = []
        self._specs: list[dict] = []
        self._concept_units: dict[str, tuple] = {}  # generated cd id -> (unit, first use)

    # -- public API -------------------------------------------------------------------------------

    def add_asset(self, spec: dict) -> None:
        tag = spec["tag"]
        for sm_spec in spec.get("submodels", []):
            id_short = sm_spec.get("idShort") or self.library.get(sm_spec["template"])["idShort"]
            version = sm_spec["template"].rsplit("-", 1)[-1].split(".")[0]
            self._sm_ids[f"{tag}/{id_short}"] = ids.submodel_id(tag, id_short, version)
        self._specs.append(spec)

    def build(self) -> dict:
        for spec in self._specs:
            self._build_asset(spec)
        for ref in self._pending:
            self._resolve_pending(ref)
        cds = self.library.concept_descriptions_for(self.submodels)
        cds += self._template_concepts({cd["id"] for cd in cds})
        return {"assetAdministrationShells": self.shells, "submodels": self.submodels,
                "conceptDescriptions": cds}

    def _template_concepts(self, known: set[str]) -> list[dict]:
        """Concept descriptions for template semantic ids that have none in the library (e.g. ECLASS IRDIs of
        IDTA AssetLocation): name and definition from the template element, unit from TEMPLATE_UNITS."""
        out: dict[str, dict] = {}
        for element in _properties(self.submodels):
            sem = (element.get("semanticId") or {}).get("keys", [{}])[0].get("value")
            if not sem or sem in known or sem in out:
                continue
            definition = {d["language"]: d["text"] for d in element.get("description") or []}
            out[sem] = concept_description(sem, {
                "idShort": element.get("idShort", "Concept"),
                "valueType": element.get("valueType", "xs:string"),
                "unit": TEMPLATE_UNITS.get(sem), "preferredName": {"en": _words(element.get("idShort", ""))},
                "definition": definition or {"en": element.get("idShort", "")}}, element["modelType"])
        return list(out.values())

    # -- assets -----------------------------------------------------------------------------------

    def _build_asset(self, spec: dict) -> None:
        tag = spec["tag"]
        aas_id = ids.aas_id(tag)
        self.shell_files[aas_id] = set()
        sm_refs = []
        for sm_spec in spec.get("submodels", []):
            sm = self._build_submodel(tag, sm_spec, aas_id)
            sm_refs.append({"type": "ModelReference", "keys": [{"type": "Submodel", "value": sm["id"]}]})
        shell = {"modelType": "AssetAdministrationShell", "id": aas_id, "idShort": spec["idShort"],
                 "administration": {"version": "1", "revision": "0"},
                 "assetInformation": self._asset_information(spec, aas_id), "submodels": sm_refs}
        for key in ("displayName", "description"):
            if spec.get(key):
                shell[key] = mlp_value(spec[key])
        if spec.get("derivedFrom"):
            shell["derivedFrom"] = self._model_ref(
                [("AssetAdministrationShell", ids.aas_id(spec["derivedFrom"]))])
        self.shells.append(shell)

    def _asset_information(self, spec: dict, aas_id: str) -> dict:
        info = {"assetKind": spec.get("kind", "Instance"), "globalAssetId": ids.asset_id(spec["tag"])}
        if spec.get("assetType"):
            info["assetType"] = spec["assetType"]
        specific = [{"name": k, "value": str(v)} for k, v in (spec.get("specificAssetIds") or {}).items()]
        if specific:
            info["specificAssetIds"] = specific
        thumbnail = spec.get("thumbnail")
        if isinstance(thumbnail, dict):  # {path: absolute URL, contentType} - e.g. the type's thumbnail
            info["defaultThumbnail"] = dict(thumbnail)
        elif thumbnail:
            thumb = file_value(self._embed(thumbnail, spec["tag"], aas_id))
            info["defaultThumbnail"] = {"path": thumb["value"], "contentType": thumb["contentType"]}
        return info

    def _type_concepts(self, submodel: dict, concepts: dict[str, dict], where: str) -> None:
        """IEC 61360 concept descriptions for extra properties: one concept per name and unit; only numbers
        may have a unit. A generic name used with several value types (Min, Default, ...) gets one concept per
        type (`.../property/Min/int`); the element's semanticId is adjusted accordingly."""
        for element in _properties(submodel):
            keys = (element.get("semanticId") or {}).get("keys", [])
            if not keys or keys[0]["value"] not in concepts:
                continue
            spec = dict(concepts[keys[0]["value"]], valueType=element.get("valueType", "xs:string"))
            keys[0]["value"] = self._concept_for(keys[0]["value"], spec, where)

    def _concept_for(self, cd_id: str, spec: dict, where: str) -> str:
        if spec.get("unit") and spec["valueType"] not in NUMERIC:
            raise ValueError(f"{where}: {spec['idShort']} has unit '{spec['unit']}' but valueType "
                             f"{spec['valueType']} (IEC 61360: units only for measures)")
        known = self._concept_units.setdefault(cd_id, (spec.get("unit"), spec["valueType"], where))
        if known[0] != spec.get("unit"):
            raise ValueError(f"concept {cd_id}: unit '{spec.get('unit')}' in {where} differs from "
                             f"'{known[0]}' in {known[2]} - use conceptName to separate the concepts")
        target = cd_id if known[1] == spec["valueType"] else f"{cd_id}/{spec['valueType'].split(':')[-1]}"
        if target not in self.library.concept_descriptions:
            text = spec.get("description") or {"en": _words(spec["idShort"])}
            self.library.concept_descriptions[target] = concept_description(target, {
                "idShort": spec["idShort"], "valueType": spec["valueType"], "unit": spec.get("unit"),
                "preferredName": text, "definition": text}, spec["modelType"])
        return target

    def _build_submodel(self, tag: str, sm_spec: dict, aas_id: str) -> dict:
        template = self.library.get(sm_spec["template"])
        id_short = sm_spec.get("idShort") or template["idShort"]
        values = self._substitute(sm_spec.get("values") or {}, tag, aas_id)
        result = instantiate(template, values, self._sm_ids[f"{tag}/{id_short}"], self._resolver, id_short)
        key = f"{tag}/{id_short}"
        self._type_concepts(result.submodel, result.concepts, key)
        if result.missing:
            self.report.missing[key] = result.missing
        if result.unknown:
            self.report.unknown[key] = result.unknown
        if sm_spec.get("semanticId"):
            result.submodel["semanticId"] = {"type": "ExternalReference",
                                             "keys": [{"type": "GlobalReference",
                                                       "value": sm_spec["semanticId"]}]}
        self.submodels.append(result.submodel)
        return result.submodel

    # -- values, references, files ----------------------------------------------------------------

    def _substitute(self, node, tag: str, aas_id: str):
        if isinstance(node, dict):
            return {k: self._substitute(v, tag, aas_id) for k, v in node.items()}
        if isinstance(node, list):
            return [self._substitute(v, tag, aas_id) for v in node]
        if isinstance(node, str):
            if node.startswith("repo:"):
                return self._embed(node, tag, aas_id)
            if node.startswith(("sm:SELF/", "aas:SELF")):
                node = node.replace("SELF", tag, 1)
            return VAR.sub(lambda m: self._identifier(m.group(1), SELF.sub(tag, m.group(2), count=1)), node)
        return node

    def _identifier(self, kind: str, target: str) -> str:
        if kind == "asset":
            return ids.asset_id(target)
        if kind == "aas":
            return ids.aas_id(target)
        return self._sm_ids[target]

    def _embed(self, repo_path: str, tag: str, aas_id: str) -> str:
        rel = repo_path.removeprefix("repo:")
        # OPC part names are case-insensitive; lower case avoids mismatches in package checkers
        package_path = f"/aasx/files/{tag}/{PurePosixPath(rel).name}".lower()
        self.files[package_path] = rel
        self.shell_files[aas_id].add(package_path)
        return package_path

    def _resolver(self, key: str) -> dict:
        kind, _, target = key.partition(":")
        if kind == "global":
            return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": target}]}
        if kind == "aas":
            return self._model_ref([("AssetAdministrationShell", ids.aas_id(target))])
        pending = {"__pending__": target}
        self._pending.append(pending)
        return pending

    def _resolve_pending(self, ref: dict) -> None:
        target = ref.pop("__pending__")
        sm_key, _, path = target.partition("#")
        sm_id = self._sm_ids[sm_key]
        keys = [("Submodel", sm_id)]
        if path:
            sm = next(s for s in self.submodels if s["id"] == sm_id)
            keys += _element_keys(sm["submodelElements"], path.split("."))
        ref.update(self._model_ref(keys))

    @staticmethod
    def _model_ref(keys: list[tuple[str, str]]) -> dict:
        return {"type": "ModelReference", "keys": [{"type": t, "value": v} for t, v in keys]}


def _element_keys(elements: list[dict], path: list[str]) -> list[tuple[str, str]]:
    """Reference keys for an idShort path; numeric parts address SubmodelElementList items by index."""
    keys = []
    for part in path:
        if part.isdigit():
            el = elements[int(part)]
        else:
            el = next((e for e in elements if e.get("idShort") == part), None)
        if el is None:
            raise KeyError(f"reference path element '{part}' not found")
        keys.append((el["modelType"], part))
        elements = el.get("value") or el.get("statements") or []
    return keys


def _properties(node):
    """All Property / Range / MultiLanguageProperty elements below `node`."""
    if isinstance(node, dict):
        if node.get("modelType") in ("Property", "Range", "MultiLanguageProperty"):
            yield node
        for value in node.values():
            yield from _properties(value)
    elif isinstance(node, list):
        for value in node:
            yield from _properties(value)


def _words(id_short: str) -> str:
    """CamelCase idShort -> lower-case words (preferred name)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", id_short).lower() or id_short
