"""MES order handling and passport retention without servers: lots booked to the running order, ERP
confirmations (B2MML-like), counter restart of a new session, and the store policy that keeps the passports of
shipped parts across sessions while session data is removed."""

from __future__ import annotations

import httpx
import pytest

from mes.handlers import OrderHandlers
from mes.orders import ActiveOrder, ErpClient, performance
from mes.store import WorkpieceStore
from vf_common import ids


def test_consumption_per_lot_and_performance_payload():
    order = ActiveOrder({"ScrewM5x16": 8, "Barrel": 1})
    order.start("PO-2026-0001")
    order.book_release("PO-2026-0001", "Barrel=L2609-0419;ScrewM5x16=NRN-26-33870")
    order.book_release("PO-2026-0001", "Barrel=L2609-0420;ScrewM5x16=NRN-26-33870")
    order.book_release("", "Barrel=L0")  # no order running: not booked
    consumed = {(c["MaterialDefinitionID"], c["MaterialLotID"]): c["Quantity"]["QuantityString"]
                for c in order.consumption("PO-2026-0001")}
    assert consumed == {("5032-1001", "L2609-0419"): "1", ("5032-1001", "L2609-0420"): "1",
                        ("9001-0516", "NRN-26-33870"): "16"}
    doc = performance("PO-2026-0001", "Completed", 2, 1, order.consumption("PO-2026-0001"))
    response = doc["OperationsResponse"]
    assert response["OperationsRequestID"] == "PO-2026-0001" and response["ResponseState"] == "Completed"
    produced = {m["MaterialUse"]: m["Quantity"]["QuantityString"]
                for m in response["SegmentResponse"]["MaterialProducedActual"]}
    assert produced == {"Produced": "2", "Scrap": "1"}


def _erp(status: int | None):
    def handler(request):
        if status is None:
            raise httpx.ConnectError("refused")
        return httpx.Response(status, json={})
    client = ErpClient("http://erp:8098")
    client.http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_erp_client_strict_and_best_effort():
    assert _erp(200).confirm("PO-1", "Completed", 1, 0, strict=True) is True
    assert _erp(404).confirm("PO-1", "Completed", 1, 0, strict=True) is False  # not an ERP order
    assert _erp(None).confirm("PO-1", "InProcess", 1, 0) is False
    with pytest.raises(RuntimeError):
        _erp(None).confirm("PO-1", "Completed", 1, 0, strict=True)
    assert ErpClient(None).confirm("PO-1", "Completed", 1, 0, strict=True) is False


class _Aas:
    def __init__(self, good: int, bad: int):
        self.good, self.bad = good, bad

    def get_value(self, sm_id, path=None):
        return {"parts_ok": self.good, "parts_nok": self.bad}


def test_order_progress_survives_a_counter_restart():
    handlers = OrderHandlers(_Aas(3, 1))
    v = {"orderId": "PO-1", "quantity": 10, "goodAtStart": 40, "rejectsAtStart": 5, "checkGood": 48,
         "checkRejects": 6, "produced": 8, "rejects": 1}
    result = handlers.order_progress(v)  # new session: PLC counters restarted at 3/1
    assert result["produced"] == 11 and result["rejects"] == 2 and result["orderDone"]
    assert (result["goodAtStart"], result["checkGood"]) == (-8, 0)


class _Store(WorkpieceStore):
    """WorkpieceStore on a fake AAS server (no build): shells, submodels and DppMetadata status."""

    def __init__(self, aas):
        self.aas, self.retention, self.passport_limit = aas, 500, 0
        import threading
        from collections import OrderedDict
        self._instances, self._shipped, self._lock = OrderedDict(), OrderedDict(), threading.Lock()


class _FakeAas:
    def __init__(self, parts: dict[str, str]):
        self.shells = {ids.aas_id(f"WP_{s}"): [ids.submodel_id(f"WP_{s}", n, "1")
                                               for n in ("DppMetadata", "CarbonFootprint")]
                       for s in parts}
        self.status = {ids.submodel_id(f"WP_{s}", "DppMetadata", "1"): st for s, st in parts.items()}
        self.deleted: list[str] = []

    def list_shells(self):
        return [{"id": i, "submodels": [{"keys": [{"value": sm}]} for sm in sms]}
                for i, sms in self.shells.items()]

    def list_submodels(self, semantic_id=None, semantic_key_type=None):
        return [{"id": sm, "submodelElements": [{"idShort": "dppStatus", "value": st}]}
                for sm, st in self.status.items()]

    def delete_submodel(self, sm_id):
        self.deleted.append(sm_id)

    def delete_shell(self, aas_id):
        self.deleted.append(aas_id)
        self.shells.pop(aas_id)

    def get_shell(self, aas_id):
        return None


def test_new_session_keeps_the_passports_of_shipped_parts():
    aas = _FakeAas({"PC3280_2026_000001": "Active", "PC3280_2026_000002": "Inactive",
                    "PC3280_2026_000003": "Inactive"})
    store = _Store(aas)
    assert store.clear_session() == (2, 1)
    assert list(aas.shells) == [ids.aas_id("WP_PC3280_2026_000001")]
    assert ids.submodel_id("WP_PC3280_2026_000002", "CarbonFootprint", "1") in aas.deleted  # foreign submodel
    assert store.count() == 1
    with pytest.raises(RuntimeError, match="serial number reused"):
        _ReusedSerial(store).check(ids.aas_id("WP_PC3280_2026_000001"))


class _ReusedSerial:
    """Runs the reuse check of WorkpieceStore.publish without building the AAS."""

    def __init__(self, store):
        self.store = store

    def check(self, aas_id: str) -> None:
        env = {"submodels": [{"id": "dpp", "idShort": "DppMetadata",
                              "submodelElements": [{"idShort": "dppStatus", "value": "Inactive"}]}]}
        shell = {"id": aas_id, "submodels": [{"keys": [{"value": "dpp"}]}]}
        self.store.ctx = type("Ctx", (), {"build": lambda s, specs, validate: type(
            "R", (), {"environment": {**env, "assetAdministrationShells": [shell]}})()})()
        self.store.type_spec = {}
        self.store.publish({"tag": aas_id.rsplit("/", 1)[-1]})
