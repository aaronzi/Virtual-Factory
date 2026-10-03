"""Production-based instance product carbon footprint (ISO 14067 terminology, risk R9; method in
docs/interfaces/aas-model.md §6a):

    material (A1)       sum over BoM nodes of BulkCount x PCF of the component batch built into the part
                        (suppliers.py: supplier batch AAS - primary data - else the declared type PCF)
    electricity         E_cell - E_air + E_line in kWh from the historian (process_energy.py)
    compressed air      E_air = air consumed in the cell cycle x SpecificEnergy (AC01 AAS); the cell's power
                        already contains it, so it is split off (reported separately), not added
    energy              (electricity + compressed air) x grid emission factor
    production losses   rejects report their own footprint (material + energy); good parts carry the session's
                        loss per good part (cumulative losses / cumulative good parts at packing time)
    manufacturing (A3)  energy + production losses;  total (A1-A3) = material + manufacturing

Static inputs come from the AAS (BoM of the product type, emission factor of LINE01, specific energy of
compressed air of AC01); component footprints from a SupplierFootprints source. If the historian is
unavailable, the line's energy intensity (rolling kWh per part from the AAS energy counters) is used instead
(method "fallback")."""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, replace

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.historian import InfluxError

from .process_energy import ProcessEnergy
from .suppliers import (BomLine, ComponentTypeFootprints, SupplierFootprints, material_footprint, parse_lots,
                        read_bom)

log = logging.getLogger("sustainability.carbon")


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
    components: tuple = ()       # per BoM line: {node, batch, count, pcf, source, dataQuality, ...}

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

    # -- data quality (PACT): primary = supplier-specific batch data and own measured energy ----------

    @property
    def supplier_specific_share(self) -> float:
        """% of A1 from supplier-specific batch footprints (rest: declared type averages)."""
        primary = sum(c["count"] * c["pcf"] for c in self.components if c.get("dataQuality") == "primary")
        return 100.0 * primary / self.material if self.material else 0.0

    @property
    def material_primary_share(self) -> float:
        """PACT primary data share of A1: emissions-weighted primary shares declared by the suppliers."""
        primary = sum(c["count"] * c["pcf"] * c.get("primaryShare", 0.0) / 100.0 for c in self.components
                      if c.get("dataQuality") == "primary")
        return 100.0 * primary / self.material if self.material else 0.0

    @property
    def primary_share(self) -> float:
        """PACT primary data share of A1-A3: A3 (measured energy and losses of LINE01) counts as primary."""
        primary = self.material * self.material_primary_share / 100.0 + self.manufacturing
        return 100.0 * primary / self.total if self.total else 0.0


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
    def __init__(self, aas_url: str, energy: ProcessEnergy | None, intensity: EnergyIntensity,
                 suppliers: SupplierFootprints | None = None):
        self.aas_url, self.energy, self.intensity = aas_url, energy, intensity
        self.suppliers = suppliers
        self.losses = LossAllocation()
        self._static: tuple[list[BomLine], float, float] | None = None

    def static(self) -> tuple[list[BomLine], float, float]:
        """(BoM lines, grid factor kg/kWh, compressed air Wh/Nl), read once from the AAS."""
        if self._static is None:
            aas = BasyxClient(self.aas_url)
            line = ids.submodel_id("LINE01", "EnergyConsumption", "1")
            factor = float(aas.get_value(line, "EmissionFactor"))
            air = float(aas.get_value(ids.submodel_id("AC01", "EnergyConsumption", "1"),
                                      "CompressedAir.SpecificEnergy"))
            self.suppliers = self.suppliers or ComponentTypeFootprints(aas)
            self._static = (read_bom(aas), factor, air)
            log.info("BoM %d lines, grid factor %.3f kg/kWh, air %.3f Wh/Nl", len(self._static[0]), factor,
                     air)
        return self._static

    def material(self, v: dict) -> tuple[float, tuple]:
        bom = self.static()[0]
        total, details = material_footprint(bom, parse_lots(v.get("lots")), self.suppliers)
        return total, tuple(details)

    def part(self, v: dict) -> PartFootprint:
        _, factor, air_wh_per_nl = self.static()
        material, components = self.material(v)
        rejected = int(v.get("container") or 1) == 2
        try:
            if self.energy is None:
                raise InfluxError("no historian configured", transient=True)
            energy = self.energy.for_part(v)
            air_kwh = energy.air_nl * air_wh_per_nl / 1000.0
            footprint = PartFootprint(material, max(0.0, energy.cell_kwh - air_kwh) + energy.line_kwh,
                                      air_kwh, factor, rejected, residence_s=energy.residence_s,
                                      components=components)
        except (InfluxError, KeyError, ValueError) as exc:
            log.warning("historian energy for %s unavailable (%s): fallback intensity", v.get("serial"), exc)
            footprint = PartFootprint(material, self.intensity.kwh_per_part, 0.0, factor, rejected,
                                      method="fallback", components=components)
        return self.losses.allocate(v.get("session"), footprint)
