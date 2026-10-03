"""Periodic plant data in the AAS: per device operational CO2e (EnergyConsumed x EmissionFactor) and a power
time series (IDTA TimeSeries, ring buffer of the current session), line totals in LINE01/EnergyConsumption and
the energy intensity used for the instance PCF. Reads what the bridge wrote; writes only derived values."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.uns import now_iso

from .carbon import EnergyIntensity

log = logging.getLogger("mes.plant")
ENERGY_SEMANTIC_ID = f"{ids.ID_BASE}/smt/EnergyConsumption/1/0/Submodel"
LINE = "LINE01"


@dataclass
class _Series:
    sm_id: str
    segment: dict
    record_template: dict
    records: list[dict] = field(default_factory=list)
    counter: int = 0


class PlantData:
    def __init__(self, aas: BasyxClient, intensity: EnergyIntensity, window: int = 180,
                 controller: str = "PLC01"):
        self.aas, self.intensity, self.window, self.controller = aas, intensity, window, controller
        self.devices: dict[str, str] = {}  # tag -> EnergyConsumption submodel id
        self.series: dict[str, _Series] = {}
        self.session_start = now_iso()
        self.session_t0: float | None = None

    def discover(self) -> None:
        for sm in self.aas.list_submodels(semantic_id=ENERGY_SEMANTIC_ID):
            tag = sm["id"].split("/")[5]
            self.devices[tag] = sm["id"]
            ts = self.aas.get_submodel(ids.submodel_id(tag, "PowerTimeSeries", "1"))
            if ts:
                self.series[tag] = _series(ts)
        log.info("energy submodels: %s (time series: %s)", sorted(self.devices), sorted(self.series))

    def new_session(self, t: float) -> None:
        """Energy counters of the simulation restart with each session."""
        self.session_start, self.session_t0 = now_iso(), t
        for s in self.series.values():
            s.records.clear()
            s.counter = 0
        for sm_id in self.devices.values():
            self.aas.set_value(sm_id, "MeasurementStart", self.session_start)

    def sample(self, t: float) -> None:
        if self.session_t0 is None:
            self.session_t0 = t
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
            if tag in self.series:
                self._append(self.series[tag], t, power)
        if LINE in self.devices:
            self._line_totals(total_power, total_energy, factor)
        parts = self.aas.get_value(ids.submodel_id(self.controller, "OperationalData", "1"),
                                   "ProcessValues.parts_total")
        self.intensity.add(t, total_energy, int(float(parts)))

    def _line_totals(self, power: float, energy: float, device_factor: float | None) -> None:
        sm_id = self.devices[LINE]
        factor = float(self.aas.get_value(sm_id, "EmissionFactor") or device_factor or 0)
        self.aas.set_value(sm_id, "ActualPower", round(power, 2))
        self.aas.set_value(sm_id, "EnergyConsumed", round(energy, 6))
        self.aas.set_value(sm_id, "OperationalCO2eq", round(energy * factor, 6))
        self.aas.set_value(sm_id, "LastUpdate", now_iso())

    def _append(self, s: _Series, t: float, power: float) -> None:
        s.counter += 1
        record = copy.deepcopy(s.record_template)
        record["idShort"] = f"R{s.counter:06d}"
        for prop in record["value"]:
            prop["value"] = (str(round(t - self.session_t0)) if prop["idShort"] == "Time"
                             else str(round(power, 2)))
        s.records = (s.records + [record])[-self.window:]
        segment = copy.deepcopy(s.segment)
        for el in segment["value"]:
            if el["idShort"] == "Records":
                el["value"] = s.records
            elif el["idShort"] == "RecordCount":
                el["value"] = str(len(s.records))
            elif el["idShort"] == "StartTime":
                el["value"] = self.session_start
            elif el["idShort"] == "LastUpdate":
                el["value"] = now_iso()
        self.aas.put_element(s.sm_id, "Segments.Session", segment)


def _series(ts: dict) -> _Series:
    metadata = next(e for e in ts["submodelElements"] if e["idShort"] == "Metadata")
    record = next(e for e in metadata["value"] if e["idShort"] == "Record")
    segments = next(e for e in ts["submodelElements"] if e["idShort"] == "Segments")
    session = next(e for e in segments["value"] if e["idShort"] == "Session")
    return _Series(ts["id"], session, record)
