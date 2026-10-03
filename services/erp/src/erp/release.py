"""Order release to the MES and the ERP's planning loop.

Release = BPMN message `OrderReleased` (business key = order number) that starts a ProductionOrder instance on
the MES's process engine (bpmn/production_order.bpmn) with orderId, material, quantity, dueDate,
manualContainerExchange and rejectRateLimit.

Planning loop (every few seconds):
- reconcile: a Released/InProcess order without a running ProductionOrder instance is set to Aborted (the
  engine keeps its data in memory; a restart loses running orders);
- auto release (standing order policy): if nothing is open, the oldest Created order is released; without
  one, a standing make-to-stock order of `standing_quantity` parts is created and released. The MES only
  produces against a released order, and the line keeps running because there is always one.
One order at a time per line: releasing while another order is open is refused (409 in the API).
Maintenance windows (maintenance.py, ADR-0029): while one is open nothing is released; a requested window
becomes active at the next order boundary.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from vf_common.bpmn import BpmnClient

from .maintenance import MaintenanceWindows
from .store import ErpStore, Order

log = logging.getLogger("erp.release")
PROCESS = "ProductionOrder"


@dataclass
class Settings:
    auto_release: bool = True
    standing_quantity: int = 48
    reject_rate_limit: float = 0.25
    manual_container_exchange: bool = False

    def to_dict(self) -> dict:
        return {"autoRelease": self.auto_release, "standingQuantity": self.standing_quantity,
                "rejectRateLimit": self.reject_rate_limit,
                "manualContainerExchange": self.manual_container_exchange}

    def update(self, body: dict) -> None:
        if "autoRelease" in body:
            self.auto_release = bool(body["autoRelease"])
        if "standingQuantity" in body:
            self.standing_quantity = max(1, int(body["standingQuantity"]))
        if "rejectRateLimit" in body:
            self.reject_rate_limit = min(1.0, max(0.0, float(body["rejectRateLimit"])))
        if "manualContainerExchange" in body:
            self.manual_container_exchange = bool(body["manualContainerExchange"])


class OrderRelease:
    def __init__(self, store: ErpStore, bpmn: BpmnClient, settings: Settings, reconcile_s: float = 30.0,
                 windows: MaintenanceWindows | None = None):
        self.store, self.bpmn, self.settings, self.reconcile_s = store, bpmn, settings, reconcile_s
        self.windows = windows or MaintenanceWindows()
        self._next_reconcile = 0.0
        self._adopted = False

    def release(self, order: Order) -> Order:
        """Releases one order; LINE01 runs one order at a time, so an open order blocks the release (the
        queued order is released automatically after it when auto release is on)."""
        if order.state != "Created":
            raise ValueError(f"order {order.id} is {order.state}, only Created orders can be released")
        reserved = self.windows.blocking()
        if reserved:
            raise ValueError(f"LINE01 is reserved for maintenance ({reserved[0].id}, maintenance order "
                             f"{reserved[0].maintenance_order}); {order.id} stays queued (Created)")
        busy = self.store.open_orders()
        if busy:
            raise ValueError(f"LINE01 is busy with order {busy[0].id}; {order.id} stays queued (Created)")
        variables = {"orderId": order.id, "material": order.material, "quantity": order.quantity,
                     "dueDate": order.due, "manualContainerExchange": self.settings.manual_container_exchange,
                     "rejectRateLimit": str(self.settings.reject_rate_limit)}
        if not self.bpmn.correlate("OrderReleased", order.id, variables):
            raise RuntimeError(f"{PROCESS} with message start OrderReleased is not deployed (MES not ready)")
        self.store.mark(order, "Released")
        log.info("order %s released to the MES: %d x %s, due %s", order.id, order.quantity, order.material,
                 order.due)
        return order

    def adopt_running(self) -> list[Order]:
        """At start: ProductionOrder instances the MES still runs become InProcess orders of this ERP (its
        records are in memory), so order numbers are not reused and the line is not released twice."""
        adopted = []
        for instance in self.bpmn.instances(PROCESS):
            key = instance.get("businessKey")
            if not key or self.store.get(key):
                continue
            v = self.bpmn.variables(instance["id"])
            material, quantity = str(v.get("material") or "PC3280"), int(v.get("quantity") or 0)
            adopted.append(self.store.adopt(key, material, quantity, v.get("dueDate")))
            log.info("adopted running order %s from the MES", key)
        return adopted

    def reconcile(self) -> None:
        for order in self.store.open_orders():
            if self.bpmn.count_instances(PROCESS, order.id) == 0 and order.state != "Completed":
                self.store.mark(order, "Aborted")
                log.warning("order %s: no running %s instance in the MES - aborted", order.id, PROCESS)

    def tick(self, now: float | None = None) -> Order | None:
        """One planning step; returns the order released in this step, if any."""
        now = time.monotonic() if now is None else now
        if not self._adopted:
            self.adopt_running()
            self._adopted = True
        if now >= self._next_reconcile:
            self._next_reconcile = now + self.reconcile_s
            self.reconcile()
        self.windows.update(self.store.open_orders())
        if not self.settings.auto_release or self.store.open_orders() or self.windows.blocking():
            return None
        order = self.store.next_created() or self.store.create_order(self.settings.standing_quantity,
                                                                     kind="Standing")
        return self.release(order)
