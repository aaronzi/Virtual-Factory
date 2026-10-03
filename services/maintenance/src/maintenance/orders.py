"""Maintenance orders = instances of the BPMN process MaintenanceOrder (bpmn/maintenance_order.bpmn,
deployed by the MES with all process models). Business key MO-<year>-<seq>; the sequence continues after the
highest key known to the engine (running and historic instances), so numbers are not reused while the engine
lives."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from vf_common.bpmn import BpmnClient

from .config import Component
from .prognosis import Prognosis
from .tasks import MaintenanceTask

log = logging.getLogger("maintenance.orders")
PROCESS = "MaintenanceOrder"


def _seq(key: str | None) -> int:
    suffix = (key or "").rsplit("-", 1)[-1]
    return int(suffix) if suffix.isdigit() else 0


class MaintenanceOrders:
    def __init__(self, bpmn: BpmnClient):
        self.bpmn = bpmn
        self._seq = 0
        self._lock = threading.Lock()

    def known_keys(self) -> list[str]:
        response = self.bpmn.http.get("/history/process-instance",
                                      params={"processDefinitionKey": PROCESS, "maxResults": 1000})
        return [i.get("businessKey") or "" for i in response.json()] if response.status_code == 200 else []

    def next_key(self) -> str:
        with self._lock:
            self._seq = max([self._seq, *map(_seq, self.known_keys())]) + 1
            return f"MO-{datetime.now(timezone.utc):%Y}-{self._seq:04d}"

    def running(self) -> dict[str, str]:
        """{component tag: business key} of the running MaintenanceOrder instances."""
        out = {}
        for instance in self.bpmn.instances(PROCESS):
            component = self.bpmn.variables(instance["id"]).get("component")
            if component and instance.get("businessKey"):
                out[str(component)] = instance["businessKey"]
        return out

    def open(self, component: Component, task: MaintenanceTask, p: Prognosis, summary: str) -> str:
        key = self.next_key()
        variables = {
            "component": component.tag, "componentName": component.name_en, "device": component.device,
            "maintenanceId": task.maintenance_id, "taskName": task.name_en,
            "instructions": task.instructions(),
            "summary": summary, "resetParameter": component.reset_parameter,
            "healthIndexAtOpen": round(p.health_index, 4), "rulCyclesLow": round(p.rul_cycles_low, 1),
            "rulHoursLow": round(p.rul_hours_low, 4) if p.rul_hours_low is not None else -1.0,
            "cyclesAtOpen": p.cycles, "immediate": False, "partsReplaced": True,
        }
        self.bpmn.start(PROCESS, key, variables)
        log.info("maintenance order %s started for %s (%s)", key, component.tag, task.name_en)
        return key
