"""Supplier portal without servers (ADR-0028): articles and lot formats, deterministic batch records, the
batch AAS (strict validation for every article), idempotent publication, despatch advices, REST routes."""

from __future__ import annotations

import json

import pytest

from provisioner.build import DATA_ROOT, load_yaml
from supplier.__main__ import router
from supplier.articles import Catalogue
from supplier.batch_aas import BLUEPRINT, BatchPublisher, batch_spec
from supplier.batches import batch_record
from supplier.certificate import generate
from supplier.portal import Portal, UnknownLot
from vf_common.lot_values import recycled_share

LOTS = {"DGP_EC32_F": "DGP-260914-F", "DGP_EC32_R": "DGP-260915-R", "DTS_SK_PC32": "DTS-2608-1173",
        "NRN_4762_M5X16": "NRN-26-33871", "KTW_SK53_RD": "KTW-26-0911"}


@pytest.fixture(scope="module")
def catalogue():
    return Catalogue()


class _Aas:
    """Supplier repository double: records uploads."""

    def __init__(self):
        self.shells, self.submodels, self.cds, self.files = {}, {}, set(), []

    def get_shell(self, aas_id):
        return self.shells.get(aas_id)

    def put_shell(self, shell):
        self.shells[shell["id"]] = shell

    def put_submodel(self, submodel):
        self.submodels[submodel["id"]] = submodel

    def put_concept_description(self, cd):
        self.cds.add(cd["id"])

    def put_attachment(self, sm_id, path, data, name, content_type):
        self.files.append((sm_id, path, name, data[:5]))


def test_articles_are_found_by_customer_and_supplier_numbers(catalogue):
    assert set(catalogue.articles) == set(LOTS)
    cap = catalogue.find("5032-1009")
    assert cap is catalogue.find("KTW-SK53-RD") and cap.company.name == "Kunststofftechnik Westrich GmbH"
    assert cap.owns("KTW-26-0911") and not cap.owns("L2609-0419") and not cap.owns("KTW-26-91")
    assert catalogue.find("5032-1001") is None  # in-house barrel: not a supplier article


def test_purchased_parts_of_the_plant_reference_the_supplier_product_types(catalogue):
    """Same GTIN in VF Pneumatics' purchased-part AAS (CMP_*) and in the supplier's product type AAS."""
    for article in catalogue.articles.values():
        components = [load_yaml(p) for p in sorted((DATA_ROOT / "assets").glob("CMP_*.yaml"))]
        cmp = next(c for c in components
                   if c["specificAssetIds"].get("customerPartId") == article.customer_part_id)
        assert cmp["specificAssetIds"]["gtin"] == article.gtin
        assert cmp["specificAssetIds"]["manufacturerPartId"] == article.part_id
        assert article.spec["globalAssetId"].endswith("/01/" + article.gtin)


def test_batch_records_are_deterministic_and_match_the_passport(catalogue):
    record = batch_record(catalogue.find("DGP-EC32-F"), "DGP-260914-F")
    assert record == batch_record(catalogue.find("5032-1002"), "DGP-260914-F")
    assert (record.quantity, str(record.produced)) == (180, "2026-09-14")
    assert str(record.despatched) == "2026-09-16"
    assert record.asset_id == "https://virtual-factory.example/01/04099991010019/10/DGP-260914-F"
    assert record.aas_id == "https://virtual-factory.example/druckguss-pfalz/ids/aas/BATCH_DGP_260914_F"
    lot = "DGP-260914-F"  # same shares as in the MES passport (circularity per component lot)
    assert record.recycled == (recycled_share(30, lot, "pre"), recycled_share(55, lot, "post"))
    seals = [batch_record(catalogue.find("5032-1006"), f"DTS-2608-{n}") for n in range(1172, 1180)]
    assert str(seals[0].produced) == "2026-08-24" and str(seals[1].produced) == "2026-08-27"
    assert len({s.pcf for s in seals}) > 4 and all(abs(s.pcf - 0.06) <= 0.06 * 0.08 + 1e-9 for s in seals)
    assert all(80 <= s.primary_share <= 92 for s in [record]) and seals[0].recycled is None


def test_batch_aas_of_every_article_is_valid(catalogue):
    blueprint = load_yaml(BLUEPRINT)
    for tag, lot in LOTS.items():
        aas = _Aas()
        record = batch_record(catalogue.articles[tag], lot)
        assert BatchPublisher(aas).publish(record) is True
        shell = aas.shells[record.aas_id]
        assert shell["assetInformation"]["globalAssetId"] == record.asset_id
        assert shell["derivedFrom"]["keys"][0]["value"] == f"{record.article.id_base}/aas/{tag}"
        assert len(aas.submodels) == 4 and aas.files[0][2] == f"MC-{lot}.pdf" and aas.files[0][3] == b"%PDF-"
        cf = next(s for s in aas.submodels.values() if s["idShort"] == "CarbonFootprint")
        entry = {e["idShort"]: e.get("value") for e in cf["submodelElements"][0]["value"][0]["value"]}
        assert float(entry["PcfCO2eq"]) == round(record.pcf, 4) and entry["BatchId"] == lot
        assert batch_spec(blueprint, record)["specificAssetIds"]["batchId"] == lot


def test_publication_is_idempotent(catalogue):
    aas = _Aas()
    publisher = BatchPublisher(aas)
    record = batch_record(catalogue.find("5032-1009"), "KTW-26-0911")
    assert publisher.publish(record) is True
    assert publisher.publish(record) is False and len(aas.files) == 1


def test_despatch_advice_and_rest_routes(catalogue):
    aas = _Aas()
    portal = Portal(catalogue, BatchPublisher(aas), "http://localhost:8191")
    advice = portal.despatch_advice("9001-0516", "NRN-26-33871")
    assert advice["DespatchAdviceNumber"] == "DA-NRN-26-33871" and advice["Line"]["Quantity"] == 2400
    assert advice["BatchAsset"]["Shell"].startswith("http://localhost:8191/shells/")
    assert advice["BatchAsset"]["MaterialCertificate"]["Href"].endswith("/attachment")
    assert portal.despatch_advice("9001-0516", "NRN-26-33871") is advice and len(aas.shells) == 1
    with pytest.raises(UnknownLot):
        portal.despatch_advice("5032-1002", "L2609-0419")
    api = router(portal)
    body = json.dumps({"article": "5032-1006", "batch": "DTS-2608-1173"}).encode()
    assert api.dispatch("POST", "/api/despatch-advices", body).body["Line"]["Quantity"] == 500
    in_house = b'{"article": "5032-1001", "batch": "x"}'
    assert api.dispatch("POST", "/api/despatch-advices", in_house).status == 404
    assert api.dispatch("POST", "/api/despatch-advices", b'{"article": "5032-1001"}').status == 400
    assert len(api.dispatch("GET", "/api/despatch-advices").body) == 2
    assert len(api.dispatch("GET", "/api/articles").body) == 5


def test_material_certificate_pdf(catalogue):
    pdf = generate(batch_record(catalogue.find("DGP_EC32_R"), "DGP-260915-R"))
    assert pdf.startswith(b"%PDF-1.4") and b"Inspection certificate 3.1" in pdf and b"DGP-260915-R" in pdf
    assert b"Druckguss Pfalz supplier portal" in pdf
