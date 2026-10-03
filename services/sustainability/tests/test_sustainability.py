"""Sustainability service without servers: supplier footprints per batch (interface for the supplier
environment, ADR-0028), the pcf-calculate task (idempotent per serial) and the session KPIs."""

from __future__ import annotations

import pytest

from sustainability.carbon import PartFootprint
from sustainability.handlers import FootprintHandlers
from sustainability.kpis import SessionKpis
from sustainability.suppliers import (BomLine, ChainedFootprints, ComponentFootprint, material_footprint,
                                      parse_lots)

BOM = [BomLine("Barrel", 1.0, "urn:barrel"), BomLine("ScrewM5x16", 8.0, "urn:screw")]


class _Declared:
    """Static source: declared PCF per component type, any batch."""

    def footprint(self, line, batch):
        return ComponentFootprint({"Barrel": 1.2, "ScrewM5x16": 0.01}[line.node], "component-type-aas")


class _Supplier:
    """Batch-specific source like the supplier environment (supplier_batches.py)."""

    def footprint(self, line, batch):
        if batch == "L2609-0419":
            return ComponentFootprint(0.9, "supplier-batch", batch=batch)
        return None


def test_batch_specific_supplier_footprint_falls_back_to_the_declared_value():
    source = ChainedFootprints(_Supplier(), _Declared())
    total, details = material_footprint(BOM, parse_lots("Barrel=L2609-0419;ScrewM5x16=NRN-26-33870"), source)
    assert total == pytest.approx(0.9 + 8 * 0.01)
    assert [(d["node"], d["source"]) for d in details] == [("Barrel", "supplier-batch"),
                                                           ("ScrewM5x16", "component-type-aas")]
    other, _ = material_footprint(BOM, parse_lots("Barrel=L2609-0420"), source)
    assert other == pytest.approx(1.2 + 0.08)
    assert parse_lots("Barrel=L1; =x;Piston=") == {"Barrel": "L1"}


class _Calculator:
    def __init__(self):
        self.calls = 0

    def part(self, v):
        self.calls += 1
        return PartFootprint(3.9, 0.02, 0.001, 0.363, rejected=int(v["container"]) == 2)


class _Writer:
    def __init__(self, fail_once=False):
        self.fail_once, self.written = fail_once, []

    def write(self, serial, fp, sorted_at):
        if self.fail_once:
            self.fail_once = False
            raise LookupError("workpiece AAS not found yet")
        self.written.append(serial)
        return f"sm/{serial}/CarbonFootprint"


def test_pcf_task_is_idempotent_per_serial():
    calc, writer, kpis = _Calculator(), _Writer(fail_once=True), SessionKpis()
    handlers = FootprintHandlers(calc, writer, kpis)
    v = {"serial": "PC3280-2026-000001", "session": "S-1", "container": 1, "sortedAt": "2026-10-03T10:00:19Z"}
    with pytest.raises(LookupError):
        handlers.calculate(v)  # BPMN retries the task
    result = handlers.calculate(v)
    assert calc.calls == 1 and writer.written == ["PC3280-2026-000001"]
    assert result["pcf"] == pytest.approx(3.9 + 0.021 * 0.363, abs=1e-4)
    assert result["pcfMethod"] == "historian"
    handlers.calculate({**v, "session": "S-2"})
    assert calc.calls == 2  # new session: computed again


def test_session_kpis():
    kpis = SessionKpis()
    kpis.add("A", "S-1", PartFootprint(3.9, 0.02, 0.0, 0.4, rejected=True))
    kpis.add("B", "S-1", PartFootprint(3.9, 0.02, 0.0, 0.4, loss_share=0.1))
    kpis.add("B", "S-1", PartFootprint(3.9, 0.02, 0.0, 0.4, loss_share=0.1))  # duplicate ignored
    values = kpis.values({"energyKWh": 1.0})
    assert values["goodParts"] == 1 and values["rejectedParts"] == 1
    assert values["avgPcfGoodPart"] == pytest.approx(3.9 + 0.008 + 0.1, abs=1e-4)
    assert values["productionLossesCO2eq"] == pytest.approx(3.908, abs=1e-4)
    assert values["lossShareOfA3"] == pytest.approx(0.1 / 0.108, abs=1e-3)
    assert values["line"]["energyKWh"] == 1.0
    assert kpis.get("B")["components"] == [] and kpis.recent(1)[0]["serial"] == "B"
    kpis.add("C", "S-2", PartFootprint(3.9, 0.02, 0.0, 0.4))
    assert kpis.values()["goodParts"] == 1 and kpis.values()["session"] == "S-2"
