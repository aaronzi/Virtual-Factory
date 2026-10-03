"""Periodic plant data in the AAS: per device operational CO2e (EnergyConsumed x EmissionFactor) and
LastUpdate, line totals in LINE01/EnergyConsumption, MeasurementStart per session, and the energy intensity
used as the PCF fallback. Reads what the bridge wrote; writes only derived values. The history of power and
all other outputs is in the historian (TimeSeries LinkedSegment, ADR-0019), not in the AAS."""

from __future__ import annotations

import logging

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.uns import now_iso

from .carbon import EnergyIntensity

log = logging.getLogger("sustainability.plant")
ENERGY_SEMANTIC_ID = f"{ids.ID_BASE}/smt/EnergyConsumption/1/0/Submodel"
LINE = "LINE01"


class PlantData:
    def __init__(self, aas: BasyxClient, intensity: EnergyIntensity, controller: str = "PLC01"):
        self.aas, self.intensity, self.controller = aas, intensity, controller
        self.devices: dict[str, str] = {}  # tag -> EnergyConsumption submodel id
        self.session_start = now_iso()
        self.latest: dict = {}  # line totals of the last sample (sustainability KPIs)

    def discover(self) -> None:
        for sm in self.aas.list_submodels(semantic_id=ENERGY_SEMANTIC_ID):
            self.devices[sm["id"].split("/")[5]] = sm["id"]
        log.info("energy submodels: %s", sorted(self.devices))

    def new_session(self, t: float) -> None:
        """Energy counters of the simulation restart with each session."""
        self.session_start = now_iso()
        for sm_id in self.devices.values():
            self.aas.set_value(sm_id, "MeasurementStart", self.session_start)

    def sample(self, t: float) -> None:
        total_power = total_energy = 0.0
        factor = None
        for tag, sm_id in self.devices.items():
            if tag == LINE:
                continue
            values = self.aas.get_value(sm_id)
            power, energy = float(values.get("ActualPower", 0)), float(values.get("EnergyConsumed", 0))
            factor = float(values.get("EmissionFactor", 0)) or factor
            self.aas.set_value(sm_id, "OperationalCO2eq",
                               round(energy * float(values.get("EmissionFactor", 0)), 6))
            self.aas.set_value(sm_id, "LastUpdate", now_iso())
            total_power, total_energy = total_power + power, total_energy + energy
        if LINE in self.devices:
            self._line_totals(total_power, total_energy, factor)
        parts = self.aas.get_value(ids.submodel_id(self.controller, "OperationalData", "1"),
                                   "ProcessValues.parts_total")
        self.intensity.add(t, total_energy, int(float(parts)))
        co2 = total_energy * float(factor or 0)
        self.latest = {"since": self.session_start, "powerW": round(total_power, 1),
                       "energyKWh": round(total_energy, 5), "operationalCO2eq": round(co2, 5),
                       "partsTotal": int(float(parts)), "kwhPerPart": round(self.intensity.kwh_per_part, 6)}

    def _line_totals(self, power: float, energy: float, device_factor: float | None) -> None:
        sm_id = self.devices[LINE]
        factor = float(self.aas.get_value(sm_id, "EmissionFactor") or device_factor or 0)
        self.aas.set_value(sm_id, "ActualPower", round(power, 2))
        self.aas.set_value(sm_id, "EnergyConsumed", round(energy, 6))
        self.aas.set_value(sm_id, "OperationalCO2eq", round(energy * factor, 6))
        self.aas.set_value(sm_id, "LastUpdate", now_iso())
