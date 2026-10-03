"""ERP records (in memory, ephemeral like the BPMN engine's H2 database): production orders, their
confirmations from the MES, and component batches (goods receipts, consumption).

Order states (ISA-95 request state, simplified): Created -> Released (sent to the MES) -> InProcess (first
confirmation) -> Completed (final confirmation); Aborted when the MES no longer runs a released order (e.g.
the BPMN engine was restarted). Payloads follow ISA-95 / B2MML naming (OperationsRequest,
OperationsPerformance) in JSON.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .master_data import PRODUCT, Material

OPEN = ("Released", "InProcess")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Order:
    id: str
    material: str
    quantity: int
    due: str
    kind: str = "Customer"        # Customer | Standing (make-to-stock order created by the auto release)
    state: str = "Created"
    created: str = field(default_factory=now_iso)
    released: str | None = None
    completed: str | None = None
    good: int = 0
    scrap: int = 0
    confirmations: list[dict] = field(default_factory=list)
    consumed: list[dict] = field(default_factory=list)

    def to_b2mml(self) -> dict:
        """OperationsRequest-like view with the confirmed progress (OperationsResponse summary)."""
        return {"ID": self.id, "OperationsType": "Production", "RequestState": self.state,
                "OrderKind": self.kind,
                "Created": self.created, "Released": self.released, "Completed": self.completed,
                "EndTime": self.due,
                "SegmentRequirement": {"ProcessSegmentID": "LINE01", "MaterialRequirement": [{
                    "MaterialDefinitionID": self.material, "MaterialUse": "Produced",
                    "Quantity": {"QuantityString": str(self.quantity), "UnitOfMeasure": "pcs"}}]},
                "Progress": {"Good": self.good, "Scrap": self.scrap, "Confirmations": len(self.confirmations),
                             "MaterialConsumedActual": self.consumed}}


@dataclass
class Batch:
    material: str
    lot: str
    supplier: str
    received: int = 0
    consumed: int = 0
    receipts: list[dict] = field(default_factory=list)
    source: str = "goods-receipt"  # goods-receipt | despatch-advice | consumption (retroactive backflush)
    supplier_batch: dict | None = None  # despatch advice + supplier batch AAS (receipts.py, ADR-0028)

    def to_dict(self) -> dict:
        return {"MaterialDefinitionID": self.material, "MaterialLotID": self.lot, "Supplier": self.supplier,
                "Received": self.received, "Consumed": self.consumed, "Stock": self.received - self.consumed,
                "Source": self.source, "Receipts": self.receipts,
                # batch AAS of the supplier (Digital Link, AAS id, certificate, batch PCF) - None for in-house
                # lots and receipts without despatch advice
                "SupplierBatch": self.supplier_batch}


class ErpStore:
    def __init__(self, materials: dict[str, Material]):
        self.materials = materials
        self.orders: dict[str, Order] = {}
        self.batches: dict[tuple[str, str], Batch] = {}
        self._seq = 0
        self._lock = threading.RLock()

    def create_order(self, quantity: int, material: str = PRODUCT, due: str | None = None,
                     kind: str = "Customer") -> Order:
        if material not in self.materials or self.materials[material].kind != "FinishedGood":
            raise ValueError(f"unknown finished good {material}")
        if int(quantity) <= 0:
            raise ValueError("quantity must be positive")
        with self._lock:
            self._seq += 1
            order_id = f"PO-{datetime.now(timezone.utc):%Y}-{self._seq:04d}"
            due = due or (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
            order = self.orders[order_id] = Order(order_id, material, int(quantity), due, kind)
            return order

    def adopt(self, order_id: str, material: str, quantity: int, due: str | None, state: str = "InProcess"
              ) -> Order:
        """Takes over an order the MES still runs but this (restarted, in-memory) ERP does not know."""
        with self._lock:
            suffix = order_id.rsplit("-", 1)[-1]
            if suffix.isdigit():
                self._seq = max(self._seq, int(suffix))
            order = self.orders[order_id] = Order(order_id, material, quantity, due or "", "Adopted", state)
            order.released = order.created
            return order

    def get(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def open_orders(self) -> list[Order]:
        with self._lock:
            return [o for o in self.orders.values() if o.state in OPEN]

    def next_created(self) -> Order | None:
        with self._lock:
            return next((o for o in self.orders.values() if o.state == "Created"), None)

    def mark(self, order: Order, state: str) -> None:
        with self._lock:
            order.state = state
            if state == "Released":
                order.released = now_iso()

    def confirm(self, performance: dict) -> Order:
        """Applies an OperationsPerformance of the MES; raises KeyError for an unknown order."""
        response = performance["OperationsResponse"]
        order = self.orders[response["OperationsRequestID"]]
        segment = response.get("SegmentResponse") or {}
        produced = {m["MaterialUse"]: int(m["Quantity"]["QuantityString"])
                    for m in segment.get("MaterialProducedActual", [])}
        with self._lock:
            order.good, order.scrap = produced.get("Produced", order.good), produced.get("Scrap", order.scrap)
            order.confirmations.append({"received": now_iso(), "state": response.get("ResponseState"),
                                        "good": order.good, "scrap": order.scrap})
            if response.get("ResponseState") == "Completed":
                order.state, order.completed = "Completed", now_iso()
                order.consumed = segment.get("MaterialConsumedActual", [])
                self._book_consumption(order.consumed)
            elif order.state in ("Released", "Created"):
                order.state = "InProcess"
        return order

    def receive(self, material: str, lot: str, quantity: int, source: str = "goods-receipt") -> Batch:
        """Goods receipt of a component batch."""
        if material not in self.materials or self.materials[material].kind != "Component":
            raise ValueError(f"unknown component {material}")
        with self._lock:
            batch = self.batches.get((material, lot))
            if batch is None:
                supplier = self.materials[material].supplier
                batch = self.batches[(material, lot)] = Batch(material, lot, supplier, source=source)
            batch.received += int(quantity)
            batch.receipts.append({"date": now_iso(), "quantity": int(quantity), "source": source})
            return batch

    def _book_consumption(self, consumed: list[dict]) -> None:
        for entry in consumed:
            material, lot = entry["MaterialDefinitionID"], entry["MaterialLotID"]
            quantity = int(entry["Quantity"]["QuantityString"])
            batch = self.batches.get((material, lot))
            if batch is None and material in self.materials:
                # batch consumed before its goods receipt was posted: retroactive receipt from the backflush
                batch = self.receive(material, lot, quantity, source="consumption")
            if batch is not None:
                batch.consumed += quantity
