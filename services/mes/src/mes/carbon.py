"""Instance product carbon footprint (simplified, risk R9; see docs/interfaces/aas-model.md):

    PCF = sum over BoM nodes (BulkCount x PCF of the component, A1-A3, from the component's AAS)
        + E_part x grid emission factor

E_part is the line's energy intensity (kWh per inspected part) over a rolling window of the device energy
counters in the AAS (EnergyConsumption/EnergyConsumed, written by the bridge). Everything is read from the
AAS: BoM from the product type, component PCFs via the component AAS (lookup by globalAssetId), emission
factor from the line's EnergyConsumption submodel."""

from __future__ import annotations

import base64
import json
import logging
from collections import deque

from vf_common import ids
from vf_common.basyx import BasyxClient

log = logging.getLogger("mes.carbon")
CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"


def component_footprint(aas: BasyxClient, product_tag: str = "PC3280_TYPE") -> float:
    """Sum of BulkCount x component PCF (kg CO2e) over the BoM of the product type."""
    bom = aas.get_submodel(ids.submodel_id(product_tag, "HierarchicalStructures", "1"))
    entry = next(e for e in bom["submodelElements"] if e["idShort"] == "EntryNode")
    total = 0.0
    for node in (e for e in entry.get("statements", []) if e["modelType"] == "Entity"):
        count = next((float(s["value"]) for s in node.get("statements", [])
                      if s["idShort"] == "BulkCount"), 1.0)
        pcf = _component_pcf(aas, node.get("globalAssetId"))
        if pcf is None:
            log.warning("no PCF for BoM node %s", node["idShort"])
            continue
        total += count * pcf
    return total


def _component_pcf(aas: BasyxClient, global_asset_id: str | None) -> float | None:
    if not global_asset_id:
        return None
    asset = base64.urlsafe_b64encode(json.dumps({"name": "globalAssetId", "value": global_asset_id})
                                     .encode()).decode().rstrip("=")
    response = aas.http.get("/shells", params={"assetIds": asset})
    shells = response.json().get("result", []) if response.status_code == 200 else []
    for shell in shells:
        for ref in shell.get("submodels", []):
            sm = aas.get_submodel(ref["keys"][0]["value"])
            if sm and sm.get("semanticId", {}).get("keys", [{}])[0].get("value") == CARBON_FOOTPRINT:
                return _first_pcf(sm)
    return None


def _first_pcf(sm: dict) -> float | None:
    for element in sm["submodelElements"]:
        for footprint in element.get("value") or []:
            for prop in footprint.get("value") or []:
                if prop.get("idShort") == "PcfCO2eq":
                    return float(prop["value"])
    return None


class EnergyIntensity:
    """kWh per part from (time, total energy kWh, parts) samples over a rolling window."""

    def __init__(self, window_s: float = 300.0, fallback_kwh: float = 0.002):
        self.window_s, self.fallback = window_s, fallback_kwh
        self.samples: deque[tuple[float, float, int]] = deque()

    def add(self, t: float, energy_kwh: float, parts: int) -> None:
        self.samples.append((t, energy_kwh, parts))
        while self.samples and t - self.samples[0][0] > self.window_s:
            self.samples.popleft()

    @property
    def kwh_per_part(self) -> float:
        if len(self.samples) < 2:
            return self.fallback
        (_, e0, p0), (_, e1, p1) = self.samples[0], self.samples[-1]
        return (e1 - e0) / (p1 - p0) if p1 > p0 and e1 >= e0 else self.fallback
