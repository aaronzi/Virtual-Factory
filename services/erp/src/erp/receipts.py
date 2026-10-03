"""Goods receipts of purchased component batches against the suppliers' despatch advices (ADR-0028).

Ship-to-line supply: the suppliers deliver their containers directly to the feeders of the assembly cell. When
the MES sees a lot at a feeder for the first time it reports the staging (`POST /api/material-staging`); the
ERP fetches the despatch advice (ASN) of that lot from the supplier portal and posts the goods receipt with
the supplier's quantity. The batch master record then references the supplier's batch AAS (GS1 Digital Link
of the batch = globalAssetId, AAS id, material certificate, batch PCF). In-house components (VF Pneumatics'
own lots) have no despatch advice; their batches appear with the backflush of the order confirmation."""

from __future__ import annotations

import logging
import threading

import httpx

from .master_data import Material
from .store import ErpStore

log = logging.getLogger("erp.receipts")
OWN_COMPANY = "VF Pneumatics GmbH"


class SupplierPortal:
    """Client of the suppliers' portal (services/supplier)."""

    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(timeout=timeout)

    def despatch_advice(self, material: Material, lot: str) -> dict | None:
        """Despatch advice of the lot, None if the supplier does not know it; RuntimeError if unreachable."""
        try:
            response = self.http.post(f"{self.base_url}/api/despatch-advices",
                                      json={"article": material.id, "batch": lot})
        except httpx.HTTPError as exc:
            raise RuntimeError(f"supplier portal unreachable: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise RuntimeError(f"supplier portal: HTTP {response.status_code} {response.text[:200]}")
        return response.json()


def supplier_batch(advice: dict) -> dict:
    """Reference of the batch master record to the supplier's batch (from the despatch advice)."""
    asset = advice.get("BatchAsset") or {}
    return {"DespatchAdviceNumber": advice.get("DespatchAdviceNumber"),
            "DespatchDate": advice.get("DespatchDate"),
            **{key: asset.get(key) for key in ("GlobalAssetId", "AasId", "Shell", "MaterialCertificate",
                                               "PcfCO2eqPerPiece", "PrimaryDataShare")}}


class GoodsReceipts:
    def __init__(self, store: ErpStore, portal: SupplierPortal | None = None):
        self.store, self.portal = store, portal
        self._lock = threading.Lock()  # one receipt per lot, also for concurrent staging reports

    def stage(self, material_id: str, lot: str) -> tuple[dict, bool]:
        """Line-side staging of a lot: goods receipt from the despatch advice (once per lot).
        Returns (batch or status, created). RuntimeError if the supplier portal is unreachable."""
        material = self._component(material_id)
        with self._lock:
            batch = self.store.batches.get((material_id, lot))
            if batch is not None:
                return batch.to_dict(), False
            if material.supplier == OWN_COMPANY or self.portal is None:
                status = "in-house" if material.supplier == OWN_COMPANY else "no portal"
                return _status(material, lot, status), False
            advice = self.portal.despatch_advice(material, lot)
            if advice is None:
                log.warning("no despatch advice of %s for lot %s", material.supplier, lot)
                return _status(material, lot, "no despatch advice"), False
            batch = self.store.receive(material_id, lot, int(advice["Line"]["Quantity"]), "despatch-advice")
            batch.supplier_batch = supplier_batch(advice)
            log.info("goods receipt %s lot %s (%s pcs, %s)", material_id, lot, advice["Line"]["Quantity"],
                     advice.get("DespatchAdviceNumber"))
            return batch.to_dict(), True

    def receive(self, material_id: str, lot: str, quantity: int | None) -> dict:
        """Manual goods receipt (REST); the quantity defaults to the despatch advice of a purchased lot."""
        material = self._component(material_id)
        advice = None
        if self.portal is not None and material.supplier != OWN_COMPANY:
            try:
                advice = self.portal.despatch_advice(material, lot)
            except RuntimeError as exc:
                log.warning("goods receipt %s %s without despatch advice: %s", material_id, lot, exc)
        if quantity is None:
            if advice is None:
                raise ValueError("quantity required (no despatch advice for this lot)")
            quantity = int(advice["Line"]["Quantity"])
        batch = self.store.receive(material_id, lot, int(quantity))
        if advice is not None:
            batch.supplier_batch = supplier_batch(advice)
        return batch.to_dict()

    def _component(self, material_id: str) -> Material:
        material = self.store.materials.get(material_id)
        if material is None or material.kind != "Component":
            raise ValueError(f"unknown component {material_id}")
        return material


def _status(material: Material, lot: str, status: str) -> dict:
    return {"MaterialDefinitionID": material.id, "MaterialLotID": lot, "Supplier": material.supplier,
            "Status": status}
