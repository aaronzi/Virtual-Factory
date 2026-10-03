"""ERP simulator without servers: material master, order life cycle, release via BPMN message, standing
order policy, reconciliation, confirmations with backflush of component batches, REST routes."""

from __future__ import annotations

import pytest

from erp.api import router
from erp.master_data import load_materials
from erp.receipts import GoodsReceipts
from erp.release import OrderRelease, Settings
from erp.store import ErpStore


class _Bpmn:
    def __init__(self, deployed: bool = True):
        self.deployed, self.messages, self.running = deployed, [], set()

    def correlate(self, message, business_key=None, variables=None, all_instances=False):
        if not self.deployed:
            return False
        self.messages.append((message, business_key, variables))
        self.running.add(business_key)
        return True

    def count_instances(self, process_key, business_key=None):
        return int(business_key in self.running)

    def instances(self, process_key):
        return [{"id": key, "businessKey": key} for key in sorted(self.running)]

    def variables(self, instance_id):
        return {"orderId": instance_id, "quantity": 7, "material": "PC3280", "dueDate": "2026-10-09"}


@pytest.fixture()
def erp():
    store, bpmn, settings = ErpStore(load_materials()), _Bpmn(), Settings(standing_quantity=12)
    return store, bpmn, settings, OrderRelease(store, bpmn, settings)


def _performance(order_id, state, good, scrap, consumed=None):
    produced = [{"MaterialDefinitionID": "PC3280", "MaterialUse": use, "Quantity": {"QuantityString": str(n)}}
                for use, n in (("Produced", good), ("Scrap", scrap))]
    segment = {"MaterialProducedActual": produced, "MaterialConsumedActual": consumed or []}
    return {"OperationsResponse": {"OperationsRequestID": order_id, "ResponseState": state,
                                   "SegmentResponse": segment}}


def test_material_master_from_the_asset_data():
    materials = load_materials()
    assert materials["PC3280"].kind == "FinishedGood"
    screw = materials["9001-0516"]
    assert screw.bom_node == "ScrewM5x16" and screw.bom_quantity == 8 and "Normteile" in screw.supplier
    assert materials["5032-1001"].bom_node == "Barrel"  # in-house part: article from the type's process BoM
    assert sum(m.kind == "Component" for m in materials.values()) == 9


def test_release_starts_the_production_order_process(erp):
    store, bpmn, settings, release = erp
    order = store.create_order(24, due="2026-10-05")
    release.release(order)
    message, key, variables = bpmn.messages[0]
    assert message == "OrderReleased" and key == order.id and order.state == "Released"
    assert variables == {"orderId": order.id, "material": "PC3280", "quantity": 24, "dueDate": "2026-10-05",
                         "manualContainerExchange": False, "rejectRateLimit": "0.25"}
    with pytest.raises(ValueError):
        release.release(order)  # only Created orders


def test_standing_order_policy_and_reconciliation(erp):
    store, bpmn, settings, release = erp
    first = release.tick(0.0)
    assert first.kind == "Standing" and first.quantity == 12 and first.state == "Released"
    assert release.tick(1.0) is None  # an order is open
    customer = store.create_order(5)
    with pytest.raises(ValueError, match="busy"):
        release.release(customer)  # one order at a time per line: stays queued
    bpmn.running.clear()  # engine restarted: the released order is gone
    second = release.tick(100.0)
    assert first.state == "Aborted" and second is customer and customer.state == "Released"
    settings.auto_release = False
    bpmn.running.clear()
    assert release.tick(200.0) is None and customer.state == "Aborted"


def test_restarted_erp_adopts_the_orders_the_mes_still_runs(erp):
    store, bpmn, settings, release = erp
    bpmn.running.add("PO-2026-0041")
    assert release.tick(0.0) is None  # adopted order is open: nothing new released
    adopted = store.get("PO-2026-0041")
    assert adopted.state == "InProcess" and adopted.quantity == 7 and adopted.kind == "Adopted"
    assert store.create_order(1).id.endswith("-0042")  # numbering continues after the adopted order


def test_confirmations_and_backflush_of_batches(erp):
    store, bpmn, settings, release = erp
    order = release.release(store.create_order(3))
    store.receive("5032-1006", "DTS-2608-1172", 500)
    store.confirm(_performance(order.id, "InProcess", 1, 0))
    assert order.state == "InProcess" and order.good == 1
    consumed = [{"MaterialDefinitionID": "5032-1006", "MaterialLotID": "DTS-2608-1172",
                 "Quantity": {"QuantityString": "4"}},
                {"MaterialDefinitionID": "9001-0516", "MaterialLotID": "NRN-26-33870",
                 "Quantity": {"QuantityString": "32"}}]
    store.confirm(_performance(order.id, "Completed", 3, 1, consumed))
    assert order.state == "Completed" and (order.good, order.scrap) == (3, 1)
    assert len(order.confirmations) == 2
    seal = store.batches[("5032-1006", "DTS-2608-1172")].to_dict()
    assert seal["Stock"] == 496 and seal["Source"] == "goods-receipt"
    screw = store.batches[("9001-0516", "NRN-26-33870")].to_dict()
    assert screw["Source"] == "consumption" and screw["Consumed"] == 32
    assert screw["Supplier"].startswith("Normteile")
    with pytest.raises(KeyError):
        store.confirm(_performance("PO-unknown", "Completed", 1, 0))


def test_rest_routes(erp):
    store, bpmn, settings, release = erp
    api = router(store, release, settings)
    created = api.dispatch("POST", "/api/orders", b'{"quantity": 6, "release": true}')
    assert created.status == 201 and created.body["RequestState"] == "Released"
    order_id = created.body["ID"]
    requirement = api.dispatch("GET", f"/api/orders/{order_id}").body["SegmentRequirement"]
    assert requirement["MaterialRequirement"][0]["Quantity"]["QuantityString"] == "6"
    assert api.dispatch("POST", f"/api/orders/{order_id}/release").status == 409
    assert api.dispatch("GET", "/api/orders/PO-x").status == 404
    assert api.dispatch("POST", "/api/production-performance", b'{"x": 1}').status == 400
    unknown = api.dispatch("POST", "/api/production-performance",
                           str(_performance("PO-x", "Completed", 1, 0)).replace("'", '"').encode())
    assert unknown.status == 404
    receipt = api.dispatch("POST", "/api/goods-receipts", b'{"material": "5032-1009", "lot": "KTW-26-0910", '
                                                          b'"quantity": 400}')
    assert receipt.status == 201 and receipt.body["Stock"] == 400
    assert api.dispatch("PUT", "/api/settings", b'{"autoRelease": false}').body["autoRelease"] is False
    assert "ERP simulator" in api.dispatch("GET", "/").body
    other = api.dispatch("POST", "/api/orders", b'{"quantity": 1}').body["ID"]
    assert api.dispatch("POST", f"/api/orders/{other}/release").status == 409  # line busy: queued
    store.mark(store.get(order_id), "Completed")
    bpmn.deployed = False
    assert api.dispatch("POST", f"/api/orders/{other}/release").status == 503


class _Portal:
    """Supplier portal double: despatch advices of the purchased lots it knows."""

    def __init__(self):
        self.calls, self.down = [], False

    def despatch_advice(self, material, lot):
        self.calls.append(lot)
        if self.down:
            raise RuntimeError("supplier portal unreachable")
        if not lot.startswith("DTS-"):
            return None
        return {"DespatchAdviceNumber": f"DA-{lot}", "Line": {"Quantity": 500},
                "BatchAsset": {"GlobalAssetId": f"https://virtual-factory.example/01/04099992010018/10/{lot}",
                               "AasId": "urn:aas:batch", "PcfCO2eqPerPiece": 0.061}}


def test_line_staging_posts_the_goods_receipt_from_the_despatch_advice(erp):
    store, bpmn, settings, release = erp
    portal = _Portal()
    api = router(store, release, settings, GoodsReceipts(store, portal))

    def post(path, material, lot):
        return api.dispatch("POST", path, f'{{"material": "{material}", "lot": "{lot}"}}'.encode())
    staged = post("/api/material-staging", "5032-1006", "DTS-2608-1173")
    assert staged.status == 201 and staged.body["Received"] == 500
    assert staged.body["Source"] == "despatch-advice"
    assert staged.body["SupplierBatch"]["GlobalAssetId"].endswith("/10/DTS-2608-1173")
    again = post("/api/material-staging", "5032-1006", "DTS-2608-1173")
    assert again.status == 200 and again.body["Received"] == 500 and portal.calls == ["DTS-2608-1173"]
    in_house = post("/api/material-staging", "5032-1001", "L2609-0419")
    assert in_house.body["Status"] == "in-house" and ("5032-1001", "L2609-0419") not in store.batches
    portal.down = True
    down = post("/api/material-staging", "5032-1006", "DTS-2608-1174")
    assert down.status == 503 and ("5032-1006", "DTS-2608-1174") not in store.batches
    portal.down = False
    receipt = post("/api/goods-receipts", "5032-1006", "DTS-2608-1175")
    assert receipt.status == 201 and receipt.body["Received"] == 500 and receipt.body["SupplierBatch"]
    unknown = post("/api/goods-receipts", "5032-1009", "KTW-26-0999")
    assert unknown.status == 400  # no despatch advice and no quantity
