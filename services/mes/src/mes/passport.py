"""Item-level digital product passport of a workpiece (ADR-0021): fills the passport submodels of the
blueprint for one part - component lots (as-built BoM, material composition, recycled content per lot),
as-built technical data, handover documents with the inspection certificate, and the DPP metadata (content of
the current stage, status). Pure functions on the asset spec, no I/O; the certificate PDF is rendered by
certificate.py.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from provisioner.build import DATA_ROOT, load_yaml
from vf_common import ids

from .certificate import CertificateData, generate
from .lots import NODE_OF_ARTICLE, recycled_share
from .quality import Verdict

SMT = f"{ids.ID_BASE}/smt"  # custom templates
# submodel idShort -> semantic id listed in DppMetadata.contentSpecificationIds (order of the blueprint)
CONTENT = {
    "Nameplate": "https://admin-shell.io/idta/nameplate/3/0/Nameplate",
    "TechnicalData": "0173-1#01-AHX837#002",
    "ContactInformations": "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations",
    "HandoverDocumentation": "0173-1#01-AHF578#003",
    "CarbonFootprint": "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0",
    "HierarchicalStructures": "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel",
    "ProductMaterialComposition": f"{SMT}/ProductMaterialComposition/1/0/Submodel",
    "ProductCircularity": f"{SMT}/ProductCircularity/1/0/Submodel",
    "ExecutedProcesses": "https://admin-shell.io/idta/ExecutedProcesses/1/0",
    "QualityInspection": f"{SMT}/QualityInspection/1/0/Submodel",
}
FRAGMENT = "common/product_passport_pc3280.yaml"


def values_of(spec: dict, id_short: str) -> dict:
    entry = next(s for s in spec["submodels"] if s.get("idShort", s["template"].split("-")[0]) == id_short)
    return entry["values"]


def bom_nodes(spec: dict) -> list[dict]:
    return values_of(spec, "HierarchicalStructures")["EntryNode"]["statements"]["Node"]


def lots_of(spec: dict) -> dict[str, str]:
    """{BoM node: lot} from the as-built BoM (batch nodes: statement BatchId)."""
    return {n["_idShort"]: n["statements"]["+BatchId"]["value"] for n in bom_nodes(spec)}


@lru_cache(maxsize=1)
def declared_recycled_content() -> dict[str, dict]:
    """Declared recycled content of the type per article number (shared fragment)."""
    entries = load_yaml(DATA_ROOT / FRAGMENT)["RecycledContent"].values()
    return {entry["ComponentId"]: entry for entry in entries}


def apply_lots(spec: dict, lots: dict[str, str]) -> None:
    for node in bom_nodes(spec):
        batch = node["statements"]["+BatchId"]
        old, batch["value"] = batch["value"], lots[node["_idShort"]]
        if node.get("globalAssetId"):  # purchased batch: Digital Link .../10/<lot> of the supplier batch AAS
            node["globalAssetId"] = node["globalAssetId"].replace(f"/10/{quote(old, safe='')}",
                                                                  f"/10/{quote(batch['value'], safe='')}")
        if isinstance(node.get("_displayName"), dict):  # e.g. "Seal kit, batch DTS-2608-1173"
            names = node["_displayName"]
            node["_displayName"] = {lang: text.replace(old, batch["value"]) for lang, text in names.items()}
    for material in values_of(spec, "ProductMaterialComposition")["Materials"]:
        location = material["MaterialLocation"]
        location["BatchId"] = lots[NODE_OF_ARTICLE[location["ComponentId"]]]
    declared = declared_recycled_content()
    for entry in values_of(spec, "ProductCircularity")["RecycledContentInformation"]:
        lot = lots[NODE_OF_ARTICLE[entry["ComponentId"]]]
        base = declared[entry["ComponentId"]]
        entry["BatchId"] = lot
        entry["PreConsumerShare"] = recycled_share(base["PreConsumerShare"], lot, "pre")
        entry["PostConsumerShare"] = recycled_share(base["PostConsumerShare"], lot, "post")


def apply_as_built(spec: dict, v: dict, verdict: Verdict | None) -> None:
    """Section AsBuilt of TechnicalData: values measured on this unit (cell tests, colour inspection)."""
    area = values_of(spec, "TechnicalData")["TechnicalPropertyAreas"][0]
    section = next(s for s in area["Section"] if s.get("_idShort") == "AsBuilt")
    section["+DateOfManufacture"]["value"] = _date(v["releasedAt"])
    section["+MeasuredLeakRate"]["value"] = round(float(v["leakRate"]), 2)
    section["+MeasuredStrokeTimeAdvance"]["value"] = round(float(v["strokeTime"]), 3)
    retract = _resource_value(spec, "OP60", "MeasuredStrokeTimeRetract")
    if retract is not None:
        section["+MeasuredStrokeTimeRetract"]["value"] = retract
    section["+MeasuredDeltaE76"]["value"] = round(float(v["deltaE"]), 1)
    section["+MeasuredColourLab"]["value"] = verdict.lab_text if verdict else ""


def apply_handover(spec: dict, v: dict, passed: bool) -> None:
    """The certificate (first document) only for good parts; issue date = packing date."""
    documents = values_of(spec, "HandoverDocumentation")["Documents"]
    if passed:
        documents[0]["DocumentVersions"][0]["StatusSetDate"] = _date(v["sortedAt"])
    else:
        del documents[0]


def certificate_file(spec: dict) -> str:
    """Repository-style path of the certificate's File value (after the serial replacement)."""
    version = values_of(spec, "HandoverDocumentation")["Documents"][0]["DocumentVersions"][0]
    return version["DigitalFiles"][0]["value"].removeprefix("repo:")


def certificate(spec: dict, v: dict, verdict: Verdict) -> dict[str, bytes]:
    """{file path: PDF} of the inspection certificate of a packed good part, {} otherwise."""
    if not verdict.passed:
        return {}
    data = CertificateData(
        serial=v["serial"], issued=_date(v["sortedAt"]), manufactured=_date(v["releasedAt"]),
        order_id=str(v.get("orderId") or ""), dpp_id=ids.aas_id(spec["tag"]),
        product_id=spec["globalAssetId"],
        leak_rate=float(v["leakRate"]), stroke_time=float(v["strokeTime"]), delta_e=float(v["deltaE"]),
        lab_text=verdict.lab_text, limits=verdict.limits, lots=lots_of(spec))
    return {certificate_file(spec): generate(data)}


def apply_metadata(spec: dict, kept: set[str], status: str, last_update: str) -> None:
    values = values_of(spec, "DppMetadata")
    values["contentSpecificationIds"] = [sem for id_short, sem in CONTENT.items() if id_short in kept]
    values["dppStatus"] = status
    values["lastUpdate"] = last_update


def _resource_value(spec: dict, op: str, name: str):
    run = values_of(spec, "ExecutedProcesses")["Run"][0]
    process = next((p for p in run["Process"] if p["_idShort"] == op), None)
    entry = (process or {}).get("ResourceParameters", {}).get("+" + name)
    return entry["value"] if entry else None


def _date(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()
