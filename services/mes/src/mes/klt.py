"""Contents of the KLT stations in their HierarchicalStructures submodel: station (entry node) -> Box (the KLT
on the station) -> one Node per packed workpiece (globalAssetId = the workpiece's GS1 Digital Link, ADR-0021)
with a HasPart relationship. Cleared when the KLT is exchanged."""

from __future__ import annotations

import logging
import threading

from vf_common import ids
from vf_common.basyx import BasyxClient

log = logging.getLogger("mes.klt")
CONTAINERS = {1: "KLTA01", 2: "KLTB01"}
HAS_PART = "https://admin-shell.io/idta/HierarchicalStructures/HasPart/1/0"
NODE = "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"


class KltContents:
    def __init__(self, aas: BasyxClient):
        self.aas = aas
        self._lock = threading.Lock()

    def add(self, container: int, serial: str, slot: int, global_asset_id: str | None = None) -> None:
        tag = CONTAINERS[container]
        with self._lock:
            sm, box = self._box(tag)
            node_id = serial.replace("-", "_")
            box["statements"] = [s for s in box.get("statements", []) if s.get("idShort") not in
                                 (node_id, "HasPart_" + node_id)]
            box["statements"].append(_node(node_id, serial, slot, global_asset_id))
            box["statements"].append(_has_part(sm["id"], node_id))
            self.aas.put_submodel(sm)

    def clear(self, tag: str, exchange_count: int | None = None) -> None:
        with self._lock:
            sm, box = self._box(tag)
            box["statements"] = []
            if exchange_count is not None:
                box["description"] = [
                    {"language": "en", "text": f"KLT box no. {exchange_count + 1} of the session"},
                    {"language": "de", "text": f"KLT-Behälter Nr. {exchange_count + 1} der Sitzung"}]
            self.aas.put_submodel(sm)

    def _box(self, tag: str) -> tuple[dict, dict]:
        sm = self.aas.get_submodel(ids.submodel_id(tag, "HierarchicalStructures", "1"))
        if sm is None:
            raise RuntimeError(f"{tag} has no HierarchicalStructures submodel")
        entry = next(e for e in sm["submodelElements"] if e["idShort"] == "EntryNode")
        box = next(e for e in entry["statements"] if e.get("idShort") == "Box")
        return sm, box


def _node(node_id: str, serial: str, slot: int, global_asset_id: str | None) -> dict:
    return {"modelType": "Entity", "idShort": node_id, "entityType": "SelfManagedEntity",
            "globalAssetId": global_asset_id or ids.asset_id("WP_" + node_id),
            "semanticId": _ref(NODE),
            "displayName": [
                {"language": "en", "text": f"Profile cylinder PC-32-80-DA-M, serial {serial}"},
                {"language": "de", "text": f"Profilzylinder PC-32-80-DA-M, Seriennummer {serial}"}],
            "description": [{"language": "en", "text": f"Cylinder {serial}, slot {slot + 1}"},
                            {"language": "de", "text": f"Zylinder {serial}, Fach {slot + 1}"}]}


def _has_part(sm_id: str, node_id: str) -> dict:
    base = [{"type": "Submodel", "value": sm_id}, {"type": "Entity", "value": "EntryNode"},
            {"type": "Entity", "value": "Box"}]
    return {"modelType": "RelationshipElement", "idShort": "HasPart_" + node_id, "semanticId": _ref(HAS_PART),
            "first": {"type": "ModelReference", "keys": base},
            "second": {"type": "ModelReference", "keys": base + [{"type": "Entity", "value": node_id}]}}


def _ref(value: str) -> dict:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": value}]}
