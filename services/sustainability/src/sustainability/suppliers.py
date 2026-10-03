"""Supplier footprints of the purchased components (A1) - per component and batch.

    SupplierFootprints.footprint(line, batch) -> ComponentFootprint | None

`line` is a node of the product type's bill of material (HierarchicalStructures of PC3280_TYPE: idShort,
BulkCount, globalAssetId of the component type), `batch` the lot the assembly cell built into the part
(`part_released.lots`). Sources:

- SupplierBatchFootprints (supplier_batches.py, ADR-0028): the CarbonFootprint of the supplier's batch AAS in
  the supplier environment, found via federated discovery by the batch's GS1 Digital Link - batch-specific
  primary data.
- ComponentTypeFootprints: the CarbonFootprint submodel of the component type AAS found via the node's
  globalAssetId - the declared average PCF, identical for every batch (secondary data in PACT terms). In-house
  components and batches without a supplier record get this value.
ChainedFootprints puts the supplier source in front of the static one. Every footprint carries its data
quality (PACT data quality concept): `primary` (supplier-specific batch data, with the supplier's own primary
data share) or `secondary` (declared type average).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Protocol

from vf_common import ids
from vf_common.basyx import BasyxClient

log = logging.getLogger("sustainability.suppliers")
CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"


@dataclass(frozen=True)
class BomLine:
    node: str                    # BoM node idShort, e.g. "Barrel" (= key of part_released.lots)
    count: float                 # BulkCount
    global_asset_id: str | None  # component type


@dataclass(frozen=True)
class ComponentFootprint:
    pcf_kg: float                # kg CO2e per piece (A1-A3 of the supplier)
    source: str                  # "supplier-batch" | "component-type-aas"
    reference: str = ""          # submodel id the value was read from
    batch: str | None = None     # batch the value applies to (None = any batch)
    data_quality: str = "secondary"  # "primary" (supplier-specific batch data) | "secondary" (type average)
    primary_share: float = 0.0   # % of this PCF from primary data, as declared by the supplier (PACT)
    asset_id: str = ""           # globalAssetId of the batch (supplier batch AAS)


class SupplierFootprints(Protocol):
    def footprint(self, line: BomLine, batch: str | None) -> ComponentFootprint | None: ...


def read_bom(aas: BasyxClient, product_tag: str = "PC3280_TYPE") -> list[BomLine]:
    """Component lines of the product type's BoM (first level below the entry node)."""
    bom = aas.get_submodel(ids.submodel_id(product_tag, "HierarchicalStructures", "1"))
    entry = next(e for e in bom["submodelElements"] if e["idShort"] == "EntryNode")
    lines = []
    for node in (e for e in entry.get("statements", []) if e["modelType"] == "Entity"):
        count = next((float(s["value"]) for s in node.get("statements", [])
                      if s["idShort"] == "BulkCount"), 1.0)
        lines.append(BomLine(node["idShort"], count, node.get("globalAssetId")))
    return lines


class ComponentTypeFootprints:
    """Declared PCF of the component type (CarbonFootprint of its AAS); the batch is ignored."""

    def __init__(self, aas: BasyxClient):
        self.aas = aas
        self._cache: dict[str, ComponentFootprint | None] = {}

    def footprint(self, line: BomLine, batch: str | None) -> ComponentFootprint | None:
        if not line.global_asset_id:
            return None
        if line.global_asset_id not in self._cache:
            self._cache[line.global_asset_id] = self._lookup(line.global_asset_id)
        return self._cache[line.global_asset_id]

    def _lookup(self, global_asset_id: str) -> ComponentFootprint | None:
        asset = base64.urlsafe_b64encode(json.dumps({"name": "globalAssetId", "value": global_asset_id})
                                         .encode()).decode().rstrip("=")
        response = self.aas.http.get("/shells", params={"assetIds": asset})
        shells = response.json().get("result", []) if response.status_code == 200 else []
        for shell in shells:
            for ref in shell.get("submodels", []):
                sm = self.aas.get_submodel(ref["keys"][0]["value"])
                if sm and sm.get("semanticId", {}).get("keys", [{}])[0].get("value") == CARBON_FOOTPRINT:
                    pcf = first_pcf(sm)
                    return None if pcf is None else ComponentFootprint(pcf, "component-type-aas", sm["id"])
        return None


class ChainedFootprints:
    """First source that knows the component/batch wins (e.g. supplier environment, then the static type)."""

    def __init__(self, *sources: SupplierFootprints):
        self.sources = sources

    def footprint(self, line: BomLine, batch: str | None) -> ComponentFootprint | None:
        for source in self.sources:
            found = source.footprint(line, batch)
            if found is not None:
                return found
        return None


def material_footprint(bom: list[BomLine], lots: dict[str, str],
                       source: SupplierFootprints) -> tuple[float, list[dict]]:
    """A1 of one part: sum of BulkCount x component PCF of the batch built in; with the per-line details."""
    total, details = 0.0, []
    for line in bom:
        batch = lots.get(line.node)
        found = source.footprint(line, batch)
        if found is None:
            log.warning("no PCF for BoM node %s (batch %s)", line.node, batch)
            continue
        total += line.count * found.pcf_kg
        details.append({"node": line.node, "batch": batch, "count": line.count, "pcf": found.pcf_kg,
                        "source": found.source, "dataQuality": found.data_quality,
                        "primaryShare": found.primary_share, "assetId": found.asset_id})
    return total, details


def parse_lots(text: str | None) -> dict[str, str]:
    """'Barrel=L2609-0419;EndCapFront=DGP-260914-F' -> {node: lot}."""
    pairs = (pair.partition("=") for pair in (text or "").split(";"))
    return {node.strip(): lot.strip() for node, _, lot in pairs if node.strip() and lot.strip()}


def first_pcf(sm: dict) -> float | None:
    value = first_entry(sm).get("PcfCO2eq")
    return None if value is None else float(value)


def first_entry(sm: dict) -> dict[str, str]:
    """{idShort: value} of the Properties of the first ProductCarbonFootprint entry ({} if none)."""
    for element in sm["submodelElements"]:
        for footprint in element.get("value") or []:
            return {p["idShort"]: p.get("value") for p in footprint.get("value") or []
                    if p.get("modelType") == "Property"}
    return {}
