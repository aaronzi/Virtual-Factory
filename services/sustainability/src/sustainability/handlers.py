"""External task `pcf-calculate` of the WorkpieceLifecycle process (bpmn/workpiece_lifecycle.bpmn): runs after
the MES has recorded the packing (OP90, KLT location) and writes the production-based PCF of the part into its
CarbonFootprint submodel. Idempotent per serial (a retried task reuses the footprint, losses are allocated
once)."""

from __future__ import annotations

import logging
import threading

from .carbon import FootprintCalculator, PartFootprint
from .footprint_aas import FootprintWriter
from .kpis import SessionKpis

log = logging.getLogger("sustainability.handlers")


class FootprintHandlers:
    def __init__(self, calculator: FootprintCalculator, writer: FootprintWriter, kpis: SessionKpis):
        self.calculator, self.writer, self.kpis = calculator, writer, kpis
        self._done: dict[str, PartFootprint] = {}
        self._session: str | None = None
        self._lock = threading.Lock()

    def topics(self) -> dict:
        return {"pcf-calculate": self.calculate}

    def calculate(self, v: dict) -> dict:
        serial, session = str(v["serial"]), v.get("session")
        with self._lock:
            if session != self._session:
                self._session, self._done = session, {}
            fp = self._done.get(serial)
            if fp is None:
                fp = self._done[serial] = self.calculator.part(v)
        sm_id = self.writer.write(serial, fp, str(v["sortedAt"]))
        self.kpis.add(serial, session, fp)
        log.info("PCF %s: %.4f kg CO2e (A1 %.4f, A3 %.5f, %s%s)", serial, fp.total, fp.material,
                 fp.manufacturing, fp.method, ", reject" if fp.rejected else "")
        return {"pcf": round(fp.total, 4), "pcfMethod": fp.method, "carbonFootprintSubmodel": sm_id}
