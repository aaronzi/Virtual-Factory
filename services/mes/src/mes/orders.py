"""Production orders in the MES: the order running on the line (released by the ERP through the
ProductionOrder process, ADR-0025) and what it consumed, and the confirmations sent back to the ERP.

- `ActiveOrder`: set by line-start, cleared by order-close; workpieces released meanwhile carry its number
  (process variable orderId, inspection certificate) and their component lots are booked to it.
- `ErpClient`: ISA-95 (B2MML-like) OperationsPerformance JSON to the ERP
  (`POST {erp}/api/production-performance`): status InProcess on start and on progress (best effort, logged),
  Completed in the task order-confirm with the actual material consumption per lot (MaterialConsumedActual;
  strict: an unreachable ERP fails the task, Operaton retries it). Orders unknown to the ERP (HTTP 404, e.g.
  started manually in Tasklist) are not confirmed.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from datetime import datetime, timezone

import httpx

from vf_common.auth import service_auth

from .lots import COMPONENTS, parse

log = logging.getLogger("mes.orders")
PRODUCT = "PC3280"


class ActiveOrder:
    def __init__(self, bulk_counts: dict[str, float] | None = None):
        self.order_id = ""
        self.bulk_counts = bulk_counts or {}
        self._consumed: dict[str, Counter] = {}  # order -> (node, lot) -> parts built
        self._lock = threading.Lock()

    def start(self, order_id: str) -> None:
        with self._lock:
            self.order_id = order_id
            self._consumed.setdefault(order_id, Counter())

    def close(self) -> None:
        with self._lock:
            self.order_id = ""

    def book_release(self, order_id: str, lots: str | None) -> None:
        """Books the component lots of one released part to the order (actual consumption)."""
        if not order_id:
            return
        with self._lock:
            counter = self._consumed.setdefault(order_id, Counter())
            for node, lot in parse(lots).items():
                counter[(node, lot)] += 1

    def consumption(self, order_id: str) -> list[dict]:
        """MaterialConsumedActual of the order: article, lot, quantity (parts x BulkCount)."""
        with self._lock:
            counter = self._consumed.get(order_id, Counter())
            return [{"MaterialDefinitionID": COMPONENTS[node], "MaterialLotID": lot, "BomNode": node,
                     "Quantity": {"QuantityString": str(int(n * self.bulk_counts.get(node, 1.0))),
                                  "UnitOfMeasure": "pcs"}}
                    for (node, lot), n in sorted(counter.items())]

    def forget(self, order_id: str) -> None:
        with self._lock:
            self._consumed.pop(order_id, None)


def performance(order_id: str, status: str, good: int, scrap: int,
                consumed: list[dict] | None = None) -> dict:
    """B2MML-like OperationsPerformance / OperationsResponse of one production request."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    produced = [{"MaterialDefinitionID": PRODUCT, "MaterialUse": "Produced", "Quantity": {
        "QuantityString": str(good), "UnitOfMeasure": "pcs"}},
        {"MaterialDefinitionID": PRODUCT, "MaterialUse": "Scrap", "Quantity": {
            "QuantityString": str(scrap), "UnitOfMeasure": "pcs"}}]
    return {"ID": f"{order_id}-{now}", "OperationsType": "Production", "PublishedDate": now,
            "OperationsResponse": {"OperationsRequestID": order_id, "ResponseState": status,
                                   "SegmentResponse": {"ProcessSegmentID": "LINE01",
                                                       "MaterialProducedActual": produced,
                                                       "MaterialConsumedActual": consumed or []}}}


class ErpClient:
    def __init__(self, base_url: str | None, timeout: float = 5.0):
        self.base_url = (base_url or "").rstrip("/")
        self.http = httpx.Client(timeout=timeout, auth=service_auth()) if self.base_url else None

    def confirm(self, order_id: str, status: str, good: int, scrap: int,
                consumed: list[dict] | None = None, strict: bool = False) -> bool:
        """True if the ERP accepted the confirmation; False without ERP or if it does not know the order."""
        if not self.http or not order_id:
            return False
        try:
            response = self.http.post(f"{self.base_url}/api/production-performance",
                                      json=performance(order_id, status, good, scrap, consumed))
        except httpx.HTTPError as exc:
            if strict:
                raise RuntimeError(f"ERP unreachable: {exc}") from exc
            log.warning("ERP unreachable, confirmation %s %s not sent: %s", order_id, status, exc)
            return False
        if response.status_code >= 500 and strict:
            raise RuntimeError(f"ERP confirmation {order_id}: HTTP {response.status_code}")
        if response.status_code >= 300:
            log.info("ERP did not accept confirmation %s %s: HTTP %s %s", order_id, status,
                     response.status_code, response.text[:200])
            return False
        return True
