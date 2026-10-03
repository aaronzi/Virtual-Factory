"""Sustainability KPIs of the current session, from the per-part footprints and the plant energy totals:

    good / rejected parts with a PCF, average PCF of a good part (A1-A3) and its A1 / A3 shares,
    energy per good part (kWh), production losses (kg CO2e of rejects), loss share of the A3 footprint,
    data quality: average PACT primary data share and share of supplier-specific batch data in A1 (ADR-0028),
    line energy and operational CO2e since the session start (LINE01/EnergyConsumption, plant_data.py).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import asdict

from .carbon import PartFootprint


class SessionKpis:
    def __init__(self, keep: int = 500):
        self.keep = keep
        self._lock = threading.Lock()
        self._clear(None)

    def reset(self, session: str | None) -> None:
        with self._lock:
            self._clear(session)

    def add(self, serial: str, session: str | None, fp: PartFootprint) -> None:
        with self._lock:
            if session and session != self.session and self.parts:
                self._clear(session)
            self.session = session or self.session
            if serial in self.parts:
                return
            self.parts[serial] = record(serial, fp)
            while len(self.parts) > self.keep:
                self.parts.popitem(last=False)
            if fp.rejected:
                self.rejected += 1
                self.losses += fp.own
                return
            self.good += 1
            self.sum_total += fp.total
            self.sum_material += fp.material
            self.sum_manufacturing += fp.manufacturing
            self.sum_energy += fp.electricity_kwh + fp.air_kwh
            self.sum_loss_share += fp.loss_share
            self.sum_primary += fp.primary_share
            self.sum_supplier += fp.supplier_specific_share

    def get(self, serial: str) -> dict | None:
        with self._lock:
            return self.parts.get(serial)

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self.parts.values())[-limit:][::-1]

    def values(self, plant: dict | None = None) -> dict:
        with self._lock:
            n = self.good or 1
            manufacturing = self.sum_manufacturing or 1.0
            return {"session": self.session, "goodParts": self.good, "rejectedParts": self.rejected,
                    "avgPcfGoodPart": round(self.sum_total / n, 4) if self.good else None,
                    "avgMaterialA1": round(self.sum_material / n, 4) if self.good else None,
                    "avgManufacturingA3": round(self.sum_manufacturing / n, 5) if self.good else None,
                    "energyPerGoodPartKWh": round(self.sum_energy / n, 6) if self.good else None,
                    "productionLossesCO2eq": round(self.losses, 4),
                    "lossShareOfA3": round(self.sum_loss_share / manufacturing, 4) if self.good else None,
                    "avgPrimaryDataShare": round(self.sum_primary / n, 1) if self.good else None,
                    "avgSupplierSpecificShareA1": round(self.sum_supplier / n, 1) if self.good else None,
                    "line": plant or {}}

    def _clear(self, session: str | None) -> None:
        self.session, self.parts = session, OrderedDict()
        self.good = self.rejected = 0
        self.sum_total = self.sum_material = self.sum_manufacturing = self.sum_energy = self.losses = 0.0
        self.sum_loss_share = self.sum_primary = self.sum_supplier = 0.0


def record(serial: str, fp: PartFootprint) -> dict:
    data = asdict(fp)
    data["components"] = list(fp.components)
    return {"serial": serial, **data, "total": round(fp.total, 6),
            "manufacturing": round(fp.manufacturing, 6), "primaryDataShare": round(fp.primary_share, 1),
            "supplierSpecificShareA1": round(fp.supplier_specific_share, 1)}
