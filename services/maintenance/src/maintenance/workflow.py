"""External-task handlers of the MaintenanceOrder process (bpmn/maintenance_order.bpmn, ADR-0029):

    maintenance-reserve        ERP maintenance window (start OrderBoundary, or Immediate if the planner
                               chose so)
    maintenance-check-line     window active = line free (order boundary reached)       -> lineFree
    maintenance-line-stop      LineControl ExecuteSkill(Maintain, Maintenance): stop, unit mode Maintenance
    maintenance-device-reset   after the technician's task: ExecuteSkill(Maintain, Maintenance,
                               {<reset parameter>: true}) -> the device confirms (cycle counter 0 on the UNS)
    maintenance-line-handback  LineControl SetUnitMode(Production), ERP window completed (the ERP releases the
                               next order, the MES starts the line); an interrupted order is restarted with
                               ExecuteSkill(Produce, Production)
    maintenance-record         MaintenanceRecord + observed Reliability in the AAS, order closed (alarm
                               cleared)

The line is commanded only through its AAS (LineControl operations delegated to the ops gateway,
ADR-0017/0020) - the device reset travels Control Component -> AID action of the device, never directly.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from .advice import iso
from .monitor import Monitor

log = logging.getLogger("maintenance.workflow")


class ErpWindows:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(timeout=timeout)

    def request(self, order: str, start: str, reason: str) -> dict:
        response = self.http.post(f"{self.base_url}/api/maintenance-windows",
                                  json={"maintenanceOrder": order, "start": start, "reason": reason})
        response.raise_for_status()
        return response.json()

    def get(self, window_id: str) -> dict | None:
        response = self.http.get(f"{self.base_url}/api/maintenance-windows/{window_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def complete(self, window_id: str) -> None:
        response = self.http.post(f"{self.base_url}/api/maintenance-windows/{window_id}/complete")
        if response.status_code != 404:  # ERP restarted: nothing to release any more
            response.raise_for_status()


class LineControl:
    """LINE01/LineControl operations through the AAS (invocation delegated to the ops gateway)."""

    def __init__(self, aas, submodel_id: Callable[[], str]):
        self.aas, self.submodel_id = aas, submodel_id

    def invoke(self, operation: str, **inputs) -> dict:
        result = self.aas.invoke(self.submodel_id(), operation, inputs, timeout_s=30)
        if result.get("Accepted") not in ("true", True):
            raise RuntimeError(f"{operation}{inputs}: {result.get('Message') or result}")
        log.info("%s%s: %s", operation, inputs, result.get("Message"))
        return result


class MaintenanceHandlers:
    def __init__(self, monitor: Monitor, line: LineControl, erp: ErpWindows, recorder,
                 verify_timeout_s: float = 15.0):
        self.monitor, self.line, self.erp, self.recorder = monitor, line, erp, recorder
        self.verify_timeout_s = verify_timeout_s

    def topics(self) -> dict:
        return {"maintenance-reserve": self.reserve, "maintenance-check-line": self.check_line,
                "maintenance-line-stop": self.line_stop, "maintenance-device-reset": self.device_reset,
                "maintenance-line-handback": self.handback, "maintenance-record": self.record}

    def reserve(self, v: dict) -> dict:
        start = "Immediate" if v.get("immediate") in (True, "true") else "OrderBoundary"
        window = self.erp.request(str(v["_businessKey"]), start,
                                  f"{v.get('taskName')} ({v.get('component')})")
        return {"windowId": window["ID"], "windowStart": start}

    def check_line(self, v: dict) -> dict:
        window = self.erp.get(str(v["windowId"]))
        if window is None:  # ERP restarted (in memory): reserve again
            return {**self.reserve(v), "lineFree": False}
        return {"lineFree": window["State"] == "Active",
                "interruptedOrder": window.get("InterruptedOrder") or ""}

    def line_stop(self, v: dict) -> dict:
        self.line.invoke("ExecuteSkill", Skill="Maintain", Mode="Maintenance", Parameters="")
        return {"maintenanceStart": time.time()}

    def device_reset(self, v: dict) -> dict:
        state = self.monitor.states[str(v["component"])]
        cycles = state.value(state.component.cycles) or v.get("cyclesAtOpen")  # retried after the reset: 0
        if v.get("partsReplaced") in (False, "false"):
            return {"cyclesAtMaintenance": int(cycles or 0), "deviceReset": False}
        parameter = str(v.get("resetParameter") or state.component.reset_parameter)
        self.line.invoke("ExecuteSkill", Skill="Maintain", Mode="Maintenance",
                         Parameters=f'{{"{parameter}": true}}')
        if not self._wait(lambda: state.live.get(state.component.cycles) in (0, "0")):
            c = state.component
            raise RuntimeError(f"{c.device} did not confirm the reset "
                               f"({c.cycles} = {state.live.get(c.cycles)})")
        return {"cyclesAtMaintenance": int(cycles or 0), "deviceReset": True}

    def handback(self, v: dict) -> dict:
        self.line.invoke("SetUnitMode", Mode="Production")
        self.erp.complete(str(v["windowId"]))
        if v.get("interruptedOrder"):  # Immediate window: the running order continues
            self.line.invoke("ExecuteSkill", Skill="Produce", Mode="Production", Parameters="")
        return {"maintenanceEnd": time.time()}

    def record(self, v: dict) -> dict:
        tag, order = str(v["component"]), str(v["_businessKey"])
        state = self.monitor.states[tag]
        downtime = max(0.0, float(v.get("maintenanceEnd") or 0) - float(v.get("maintenanceStart") or 0))
        record = {"MaintenanceOrderId": order, "MaintenanceID": v.get("maintenanceId") or "",
                  "CompletedAt": iso(datetime.now(timezone.utc).timestamp()),
                  "Technician": str(v.get("technician") or ""), "Findings": str(v.get("findings") or ""),
                  "PartsReplaced": bool(v.get("deviceReset")),
                  "CyclesAtMaintenance": int(v.get("cyclesAtMaintenance") or 0),
                  "HealthIndexBefore": float(v.get("healthIndexAtOpen") or 0), "Downtime": round(downtime, 1)}
        records = self.recorder.add_record(tag, record)
        lives = [float(r["CyclesAtMaintenance"]) for r in records
                 if str(r.get("PartsReplaced")).lower() == "true"
                 and float(r.get("CyclesAtMaintenance") or 0)]
        self.recorder.update_reliability(tag, state.component.reliability_set, lives)
        self.monitor.close_order(tag, order)
        return {"recorded": True}

    def _wait(self, condition: Callable[[], bool]) -> bool:
        deadline = time.monotonic() + self.verify_timeout_s
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(0.25)
        return condition()
