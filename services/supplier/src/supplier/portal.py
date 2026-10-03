"""Despatch advices (ASN, DESADV-like JSON) of the suppliers and the batch AAS behind them (ADR-0028).

Simulation shortcut: the suppliers ship every lot of their lot sequence; the portal materialises a lot - its
batch record, batch AAS and material certificate - when the customer first asks for the despatch advice of
that lot (ERP goods receipt, triggered by the line-side staging of the lot). The environment therefore holds
only lots that were actually delivered, and every lot the line consumes is published before its first part
is packed. Answers are idempotent (same lot -> same despatch advice, the batch AAS is created once)."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from vf_common.basyx import b64

from .articles import Catalogue
from .batch_aas import BatchPublisher
from .batches import BatchRecord, batch_record

log = logging.getLogger("supplier.portal")


class UnknownLot(LookupError):
    """The article is not a supplier article, or the lot is not in the supplier's lot format."""


class Portal:
    def __init__(self, catalogue: Catalogue, publisher: BatchPublisher, public_url: str):
        self.catalogue, self.publisher, self.public_url = catalogue, publisher, public_url.rstrip("/")
        self.advices: OrderedDict[str, dict] = OrderedDict()  # lot -> despatch advice (this run)
        self._lock = threading.Lock()

    def despatch_advice(self, article: str, lot: str) -> dict:
        """Despatch advice of a lot of the article (customer or supplier part number); creates the batch AAS
        on first request. Raises UnknownLot."""
        found = self.catalogue.find(article)
        if found is None or not found.owns(lot):
            raise UnknownLot(f"no supplier batch {lot} of article {article}")
        with self._lock:
            known = self.advices.get(lot)
        if known:
            return known
        record = batch_record(found, lot)
        created = self.publisher.publish(record)
        advice = self.advice(record, created)
        with self._lock:
            self.advices[lot] = advice
        return advice

    def advice(self, record: BatchRecord, created: bool = False) -> dict:
        article, company = record.article, record.article.company
        shell = f"{self.public_url}/shells/{b64(record.aas_id)}"
        handover = f"{article.id_base}/sm/{record.tag}/HandoverDocumentation/2"
        certificate = (f"{self.public_url}/submodels/{b64(handover)}/submodel-elements/"
                       "Documents[0].DocumentVersions[0].DigitalFiles[0]/attachment")
        return {"DespatchAdviceNumber": record.despatch_advice, "DespatchDate": record.despatched.isoformat(),
                "Supplier": {"Name": company.name, "Gln": company.gln},
                "Buyer": {"Name": "VF Pneumatics GmbH", "Gln": "4099999000012"},
                "Line": {"ManufacturerPartId": article.part_id, "CustomerPartId": article.customer_part_id,
                         "Gtin": article.gtin, "BatchId": record.lot, "Quantity": record.quantity,
                         "UnitOfMeasure": "pcs", "ProductionDate": record.produced.isoformat()},
                "BatchAsset": {"GlobalAssetId": record.asset_id, "AasId": record.aas_id, "Shell": shell,
                               "MaterialCertificate": {"DocumentId": record.certificate, "Href": certificate},
                               "PcfCO2eqPerPiece": round(record.pcf, 4),
                               "PrimaryDataShare": record.primary_share},
                "Published": "now" if created else "earlier"}
