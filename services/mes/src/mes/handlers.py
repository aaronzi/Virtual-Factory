"""External-task handlers of the two BPMN processes (bpmn/*.bpmn).

Workpiece lifecycle: write the growing workpiece instance AAS. Production order: control and follow LINE01
only through its AAS - LineControl operations (delegated to the ops gateway) and the controller's
OperationalData."""

from __future__ import annotations

import logging
import time

from vf_common import ids
from vf_common.basyx import BasyxClient

from .klt import KltContents
from .quality import Limits, evaluate
from .store import WorkpieceStore
from .workpiece import WorkpieceSpec

log = logging.getLogger("mes.handlers")
PACKML = {2: "STOPPED", 4: "IDLE", 6: "EXECUTE", 9: "ABORTED", 17: "COMPLETE", 11: "HELD", 5: "SUSPENDED"}


class WorkpieceHandlers:
    def __init__(self, store: WorkpieceStore, specs: WorkpieceSpec, limits: Limits, klt: KltContents,
                 footprint):
        self.store, self.specs, self.limits, self.klt, self.footprint = store, specs, limits, klt, footprint

    def topics(self) -> dict:
        return {"workpiece-create": self.create, "workpiece-record-inspection": self.record_inspection,
                "workpiece-record-packing": self.record_packing, "workpiece-mark-lost": self.mark_lost}

    def create(self, v: dict) -> dict:
        self.store.publish(self.specs.build(v, "released"))
        return {}

    def record_inspection(self, v: dict) -> dict:
        verdict = evaluate(v, self.limits)
        self.store.publish(self.specs.build(v, "inspected", verdict))
        return {"verdict": "Pass" if verdict.passed else "Fail",
                "plannedContainer": verdict.planned_container}

    def record_packing(self, v: dict) -> dict:
        verdict = evaluate(v, self.limits)
        footprint = self.footprint(v)  # production-based PCF (carbon.FootprintCalculator)
        self.store.publish(self.specs.build(v, "packed", verdict, footprint))
        container = int(v["container"])
        self.klt.add(container, v["serial"], int(v["slot"]))
        return {"correctContainer": container == verdict.planned_container, "pcf": round(footprint.total, 4)}

    def mark_lost(self, v: dict) -> dict:
        verdict = evaluate(v, self.limits) if v.get("deltaE") is not None else None
        self.store.publish(self.specs.build(v, "lost", verdict))
        return {}


class OrderHandlers:
    def __init__(self, aas: BasyxClient, line: str = "LINE01", controller: str = "PLC01"):
        self.aas = aas
        self.line_control = ids.submodel_id(line, "LineControl", "1")
        self.operational_data = ids.submodel_id(controller, "OperationalData", "1")

    def topics(self) -> dict:
        return {"line-start": self.line_start, "order-progress": self.order_progress,
                "line-command": self.line_command, "order-close": self.order_close,
                "line-exchange-container": self.exchange_container}

    def line_start(self, v: dict) -> dict:
        self._invoke("SetAutoExchange", Enabled=not bool(v.get("manualContainerExchange")))
        state = self._state()
        if state == "ABORTED":
            self._command("Clear")
            state = self._state()
        if state in ("STOPPED", "COMPLETE"):
            state = self._command("Reset")
        if state == "IDLE":
            # auto_start may start it itself
            state = self._wait_state("EXECUTE", 2.0) or self._command("Start")
        good, rejects = self._counters()
        log.info("order %s started: line %s, baseline %d/%d", v.get("orderId"), state, good, rejects)
        return {"goodAtStart": good, "rejectsAtStart": rejects, "checkGood": good, "checkRejects": rejects,
                "produced": 0, "rejects": 0, "orderDone": False, "rejectAlarm": False}

    def order_progress(self, v: dict) -> dict:
        good, rejects = self._counters()
        produced, order_rejects = good - int(v["goodAtStart"]), rejects - int(v["rejectsAtStart"])
        window_good, window_rejects = good - int(v["checkGood"]), rejects - int(v["checkRejects"])
        window = window_good + window_rejects
        rate = window_rejects / window if window else 0.0
        alarm = window >= 10 and rate > float(v.get("rejectRateLimit") or 0.25)
        result = {"produced": produced, "rejects": order_rejects, "rejectRate": round(rate, 3),
                  "orderDone": produced >= int(v["quantity"]), "rejectAlarm": alarm}
        if alarm or window >= 50:  # move the evaluation window
            result |= {"checkGood": good, "checkRejects": rejects}
        return result

    def line_command(self, v: dict) -> dict:
        return {"lineState": self._command(str(v["packmlCommand"]))}

    def order_close(self, v: dict) -> dict:
        self._invoke("SetAutoExchange", Enabled=True)
        log.info("order %s closed: %s good, %s rejects",
                 v.get("orderId"), v.get("produced"), v.get("rejects"))
        return {}

    def exchange_container(self, v: dict) -> dict:
        self._invoke("ExchangeContainer", Container=int(v["container"]))
        return {}

    def _command(self, command: str) -> str:
        result = self._invoke("ExecutePackMLCommand", allow_reject=command == "Stop", Command=command)
        if result.get("Accepted") not in ("true", True) and self._state() != "STOPPED":
            raise RuntimeError(f"{command}: {result.get('Message')}")
        return result.get("State") or self._state()

    def _invoke(self, operation: str, allow_reject: bool = False, **inputs) -> dict:
        result = self.aas.invoke(self.line_control, operation, inputs, timeout_s=20)
        if not allow_reject and result.get("Accepted") not in ("true", True):
            raise RuntimeError(f"{operation}{inputs}: {result.get('Message') or result}")
        return result

    def _state(self) -> str:
        value = self.aas.get_value(self.operational_data, "ProcessValues.packml_state")
        return PACKML.get(int(float(value)), str(value))

    def _wait_state(self, state: str, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._state() == state:
                return state
            time.sleep(0.5)
        return None

    def _counters(self) -> tuple[int, int]:
        values = self.aas.get_value(self.operational_data, "ProcessValues")
        return int(float(values["parts_ok"])), int(float(values["parts_nok"]))
