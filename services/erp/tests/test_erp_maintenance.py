"""Maintenance windows of the ERP (ADR-0029): no production order is released while LINE01 is reserved for
maintenance; a window requested during an order becomes active at the order boundary (or at once)."""

from __future__ import annotations

import json

import pytest

from erp.api import router
from erp.master_data import load_materials
from erp.release import OrderRelease, Settings
from erp.store import ErpStore


class _Bpmn:
    def __init__(self):
        self.running: set[str] = set()

    def correlate(self, message, business_key=None, variables=None, all_instances=False):
        self.running.add(business_key)
        return True

    def count_instances(self, process_key, business_key=None):
        return int(business_key in self.running)

    def instances(self, process_key):
        return []


@pytest.fixture()
def erp():
    store, settings = ErpStore(load_materials()), Settings(standing_quantity=4)
    return store, OrderRelease(store, _Bpmn(), settings), settings


def _complete(store, order):
    store.confirm({"OperationsResponse": {"OperationsRequestID": order.id, "ResponseState": "Completed",
                                          "SegmentResponse": {"MaterialProducedActual": []}}})


def test_window_waits_for_the_order_boundary_and_blocks_releases(erp):
    store, release, _ = erp
    running = release.tick(0.0)
    window = release.windows.request("MO-2026-0001", "OrderBoundary", "GR01 fingers worn")
    assert release.windows.request("MO-2026-0001").id == window.id, "idempotent per maintenance order"
    release.tick(1.0)
    assert window.state == "Requested", "the running order is finished first"
    _complete(store, running)
    assert release.tick(2.0) is None and window.state == "Active", "line free: no new order released"
    queued = store.create_order(2)
    with pytest.raises(ValueError, match="reserved for maintenance"):
        release.release(queued)
    release.windows.close(window.id, "Completed")
    assert release.tick(3.0) is queued and queued.state == "Released"


def test_immediate_window_is_active_at_once_and_remembers_the_interrupted_order(erp):
    store, release, _ = erp
    running = release.tick(0.0)
    window = release.windows.request("MO-2026-0002", "Immediate")
    release.tick(1.0)
    assert window.state == "Active" and window.interrupted_order == running.id
    with pytest.raises(ValueError, match="start must be one of"):
        release.windows.request("MO-3", "Tomorrow")


def test_maintenance_window_routes(erp):
    store, release, settings = erp
    api = router(store, release, settings)

    def call(method, url, body=None):
        return api.dispatch(method, url, json.dumps(body).encode() if body else b"")

    created = call("POST", "/api/maintenance-windows", {"maintenanceOrder": "MO-2026-0003", "reason": "test"})
    assert created.status == 201 and created.body["State"] == "Active", "no order open: active at once"
    window_id = created.body["ID"]
    assert call("GET", f"/api/maintenance-windows/{window_id}").body["MaintenanceOrder"] == "MO-2026-0003"
    assert call("POST", "/api/maintenance-windows", {}).status == 400
    assert call("POST", f"/api/maintenance-windows/{window_id}/complete").body["State"] == "Completed"
    assert call("POST", "/api/maintenance-windows/MW-9999/cancel").status == 404
    assert [w["State"] for w in call("GET", "/api/maintenance-windows").body] == ["Completed"]
