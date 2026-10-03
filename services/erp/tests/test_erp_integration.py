"""Order to confirmation against the running stack and factory (`uv run pytest -m integration`): a customer
order created in the ERP is released to the MES (BPMN ProductionOrder) as soon as LINE01 is free, the line
produces it and the MES confirms good quantity, scrap and the consumed component lots; the ERP books the
consumption against batches. Needs a UNS-connected factory; skipped while LINE01 is busy with an order that
needs more than 4 further parts (CI: infra/docker-compose.ci.yml sets VF_ERP_STANDING_QTY=2); waits at most
10 minutes."""

from __future__ import annotations

import time

import httpx
import pytest

pytestmark = pytest.mark.integration
ERP = "http://localhost:8098"


@pytest.fixture(scope="module")
def erp():
    try:
        settings = httpx.get(f"{ERP}/api/settings", timeout=3).json()
    except httpx.HTTPError:
        pytest.skip("ERP not running")
    httpx.put(f"{ERP}/api/settings", json={"standingQuantity": 2, "autoRelease": True}, timeout=3)
    yield
    httpx.put(f"{ERP}/api/settings", json=settings, timeout=3)


def _order(order_id: str) -> dict:
    return httpx.get(f"{ERP}/api/orders/{order_id}", timeout=5).json()


def test_customer_order_is_produced_and_confirmed(erp):
    for order in httpx.get(f"{ERP}/api/orders", params={"state": "InProcess"}, timeout=5).json():
        left = int(order["SegmentRequirement"]["MaterialRequirement"][0]["Quantity"]["QuantityString"]) - \
            order["Progress"]["Good"]
        if left > 4:
            pytest.skip(f"LINE01 busy with order {order['ID']} ({left} parts left)")
    created = httpx.post(f"{ERP}/api/orders", json={"quantity": 2}, timeout=5)
    assert created.status_code == 201 and created.json()["RequestState"] == "Created"
    order_id = created.json()["ID"]
    deadline, started = time.monotonic() + 600, None
    while time.monotonic() < deadline:
        order = _order(order_id)
        if order["RequestState"] == "Completed":
            break
        if order["RequestState"] == "InProcess" and started is None:
            started = time.monotonic()
        if started is None and time.monotonic() > deadline - 480 and not _line_produces():
            pytest.skip("no parts are produced (factory not running)")
        time.sleep(5)
    order = _order(order_id)
    assert order["RequestState"] == "Completed", order
    assert order["Progress"]["Good"] >= 2 and order["Progress"]["Confirmations"] >= 2
    consumed = order["Progress"]["MaterialConsumedActual"]
    assert {c["BomNode"] for c in consumed} >= {"Barrel", "SealKit", "ScrewM5x16"}
    batches = {(b["MaterialDefinitionID"], b["MaterialLotID"]): b
               for b in httpx.get(f"{ERP}/api/batches", timeout=5).json()}
    for entry in consumed:
        assert batches[(entry["MaterialDefinitionID"], entry["MaterialLotID"])]["Consumed"] > 0


def _line_produces() -> bool:
    orders = httpx.get(f"{ERP}/api/orders", timeout=5).json()
    return any(o["Progress"]["Confirmations"] > 1 for o in orders)
