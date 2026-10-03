"""Production-based instance product carbon footprint (ISO 14067 terminology, risk R9; method in
docs/interfaces/aas-model.md §6a):

    material (A1)       sum over BoM nodes of BulkCount x component PCF (from the component AAS)
    electricity         E_cell - E_air + E_line in kWh from the historian (process_energy.py)
    compressed air      E_air = air consumed in the cell cycle x SpecificEnergy (AC01 AAS); the cell's power
                        already contains it, so it is split off (reported separately), not added
    energy              (electricity + compressed air) x grid emission factor
    production losses   rejects report their own footprint (material + energy); good parts carry the session's
                        loss per good part (cumulative losses / cumulative good parts at packing time)
    manufacturing (A3)  energy + production losses;  total (A1-A3) = material + manufacturing

Static inputs come from the AAS (BoM of the product type, component PCFs via globalAssetId, emission factor
of LINE01, specific energy of compressed air of AC01). If the historian is unavailable, the line's energy
intensity (rolling kWh per part from the AAS energy counters) is used instead (method "fallback")."""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections import deque
from dataclasses import dataclass, replace

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.historian import InfluxError

from .process_energy import ProcessEnergy

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


@dataclass(frozen=True)
class PartFootprint:
    material: float              # kg CO2e, purchased components (A1)
    electricity_kwh: float       # electrical energy allocated to the part, without compressed air
    air_kwh: float               # electrical energy of the compressed air allocated to the part
    factor: float                # kg CO2e per kWh
    rejected: bool = False
    loss_share: float = 0.0      # kg CO2e of production losses allocated to this good part
    residence_s: float = 0.0     # release by the assembly cell -> packing
    method: str = "historian"

    @property
    def energy_co2(self) -> float:
        return (self.electricity_kwh + self.air_kwh) * self.factor

    @property
    def own(self) -> float:
        """Footprint of this unit without allocated losses."""
        return self.material + self.energy_co2

    @property
    def manufacturing(self) -> float:
        return self.energy_co2 + self.loss_share

    @property
    def total(self) -> float:
        return self.material + self.manufacturing


class LossAllocation:
    """Production losses of one session: rejects add their own footprint, each good part takes the cumulative
    losses divided by the cumulative good parts (incl. itself) at its packing time."""

    def __init__(self):
        self.session, self.losses, self.good, self.rejects = None, 0.0, 0, 0
        self._lock = threading.Lock()

    def allocate(self, session: str | None, footprint: PartFootprint) -> PartFootprint:
        with self._lock:
            if session != self.session:
                self.session, self.losses, self.good, self.rejects = session, 0.0, 0, 0
            if footprint.rejected:
                self.losses += footprint.own
                self.rejects += 1
                return footprint
            self.good += 1
            return replace(footprint, loss_share=self.losses / self.good)


class FootprintCalculator:
    def __init__(self, aas_url: str, energy: ProcessEnergy | None, intensity: EnergyIntensity):
        self.aas_url, self.energy, self.intensity = aas_url, energy, intensity
        self.losses = LossAllocation()
        self._static: tuple[float, float, float] | None = None

    def static(self) -> tuple[float, float, float]:
        """(component PCF kg, grid factor kg/kWh, compressed air Wh/Nl), read once from the AAS."""
        if self._static is None:
            aas = BasyxClient(self.aas_url)
            line = ids.submodel_id("LINE01", "EnergyConsumption", "1")
            factor = float(aas.get_value(line, "EmissionFactor"))
            air = float(aas.get_value(ids.submodel_id("AC01", "EnergyConsumption", "1"),
                                      "CompressedAir.SpecificEnergy"))
            self._static = (component_footprint(aas), factor, air)
            log.info("BoM component PCF %.4f kg CO2e, grid factor %.3f kg/kWh, air %.3f Wh/Nl", *self._static)
        return self._static

    def part(self, v: dict) -> PartFootprint:
        material, factor, air_wh_per_nl = self.static()
        rejected = int(v.get("container") or 1) == 2
        try:
            if self.energy is None:
                raise InfluxError("no historian configured", transient=True)
            energy = self.energy.for_part(v)
            air_kwh = energy.air_nl * air_wh_per_nl / 1000.0
            footprint = PartFootprint(material, max(0.0, energy.cell_kwh - air_kwh) + energy.line_kwh,
                                      air_kwh, factor, rejected, residence_s=energy.residence_s)
        except (InfluxError, KeyError, ValueError) as exc:
            log.warning("historian energy for %s unavailable (%s): fallback intensity", v.get("serial"), exc)
            footprint = PartFootprint(material, self.intensity.kwh_per_part, 0.0, factor, rejected,
                                      method="fallback")
        return self.losses.allocate(v.get("session"), footprint)
