"""Item-level digital product passport of a workpiece (ADR-0021): ids, component lots, content per stage,
inspection certificate, attachment upload."""

from __future__ import annotations

import re

import pytest

from mes import lots, passport
from mes.certificate import CertificateData, generate, sample
from mes.pdf import Page, render
from mes.quality import Limits, evaluate
from mes.store import WorkpieceStore, file_elements
from mes.workpiece import WorkpieceSpec, load_blueprint
from provisioner.build import DATA_ROOT, BuildContext, load_assets
from vf_common import ids

SERIAL = "PC3280-2026-000777"
REPORTED = ("Barrel=L2609-0424;EndCapFront=DGP-260918-F;EndCapRear=DGP-260918-R;PistonRod=L2609-2415;"
            "Piston=L2609-3390;SealKit=DTS-2608-1174;ScrewM5x16=NRN-26-33873;CushioningScrew=L2609-5371;"
            "ProtectiveCap=KTW-26-0912")
V = {"serial": SERIAL, "releasedAt": "2026-10-03T10:00:00.000Z", "leakRate": 0.41, "strokeTime": 0.318,
     "lots": REPORTED, "orderId": "PO-0042"}
INSPECTED = {"inspectedAt": "2026-10-03T10:00:11.900Z", "deltaE": 3.4, "r": 0.77, "g": 0.09, "b": 0.11}
PACKED = {**V, **INSPECTED, "sortedAt": "2026-10-03T10:00:19.000Z", "container": 1, "slot": 4}
DIGITAL_LINK = "https://virtual-factory.example/01/04099999032808/21/" + SERIAL


@pytest.fixture(scope="module")
def specs():
    thumb = {"path": "http://localhost:8091/shells/x/asset-information/thumbnail", "contentType": "image/png"}
    return WorkpieceSpec(load_blueprint(), BuildContext().positions, thumb)


def _values(spec, id_short):
    return passport.values_of(spec, id_short)


def test_lots_reported_by_the_cell_win_over_the_fallback():
    parsed = lots.parse(REPORTED)
    assert len(parsed) == 9 and parsed["EndCapRear"] == "DGP-260918-R"
    assert lots.lots_for(V, {"Barrel": "X-1"}) == parsed
    partial = lots.lots_for({"serial": SERIAL, "lots": "Barrel=L1"},
                            {"Barrel": "L2609-0419", "Piston": "P-0001"})
    assert partial == {"Barrel": "L1", "Piston": "P-0004"}


def test_recycled_share_stays_near_the_declared_average():
    shares = [lots.recycled_share(30, f"DGP-2609{d:02d}-F", "post") for d in range(1, 29)]
    assert all(25 <= s <= 35 for s in shares) and len(set(shares)) > 3
    assert lots.recycled_share(0, "L1", "pre") == 0.0


def test_dpp_id_is_the_aas_id_and_product_id_the_digital_link(specs):
    spec = specs.build(V, "released")
    meta = _values(spec, "DppMetadata")
    assert meta["digitalProductPassportId"] == "${aas:SELF}"  # resolved to ids.aas_id(tag) by the builder
    assert spec["globalAssetId"] == meta["uniqueProductIdentifier"] == DIGITAL_LINK
    env = BuildContext().build([load_assets(DATA_ROOT, {"PC3280_TYPE"})[0], spec]).environment
    shell = env["assetAdministrationShells"][1]
    assert shell["assetInformation"]["globalAssetId"] == DIGITAL_LINK
    dpp = next(sm for sm in env["submodels"] if sm["idShort"] == "DppMetadata" and "/WP_" in sm["id"])
    dpp_id = next(e["value"] for e in dpp["submodelElements"] if e["idShort"] == "digitalProductPassportId")
    assert dpp_id == shell["id"] == ids.aas_id("WP_PC3280_2026_000777")


def test_released_passport_carries_the_reported_lots(specs):
    spec = specs.build(V, "released")
    assert passport.lots_of(spec) == lots.parse(REPORTED)
    seal_kit = next(n for n in passport.bom_nodes(spec) if n["_idShort"] == "SealKit")
    assert seal_kit["_displayName"] == {"en": "Seal kit, batch DTS-2608-1174",
                                        "de": "Dichtungssatz, Charge DTS-2608-1174"}
    materials = _values(spec, "ProductMaterialComposition")["Materials"]
    magnet = next(m for m in materials if m["MaterialLocation"]["ComponentName"] == "Piston magnet ring")
    assert magnet["MaterialLocation"]["BatchId"] == "L2609-3390"
    recycled = _values(spec, "ProductCircularity")["RecycledContentInformation"]
    rear = next(r for r in recycled if r["ComponentId"] == "5032-1003")
    assert rear["BatchId"] == "DGP-260918-R" and 47 <= rear["PostConsumerShare"] <= 63
    op40 = next(p for p in _values(spec, "ExecutedProcesses")["Run"][0]["Process"] if p["_idShort"] == "OP40")
    assert op40["ProcessBoM"]["+ScrewLot"]["value"] == "NRN-26-33873"
    meta = _values(spec, "DppMetadata")
    assert passport.CONTENT["TechnicalData"] not in meta["contentSpecificationIds"]
    assert passport.CONTENT["HierarchicalStructures"] in meta["contentSpecificationIds"]


def test_packed_good_part_has_full_passport_and_certificate(specs):
    v = PACKED
    verdict = evaluate(v, Limits())
    spec = specs.build(v, "packed", verdict, pcf=3.9)
    meta = _values(spec, "DppMetadata")
    assert meta["contentSpecificationIds"] == list(passport.CONTENT.values())
    assert meta["dppStatus"] == "Active"
    section = _values(spec, "TechnicalData")["TechnicalPropertyAreas"][0]["Section"][-1]
    assert section["+MeasuredLeakRate"]["value"] == 0.41 and section["+MeasuredDeltaE76"]["value"] == 3.4
    documents = _values(spec, "HandoverDocumentation")["Documents"]
    assert len(documents) == 5 and documents[0]["DocumentIds"][0]["DocumentIdentifier"] == "IC-" + SERIAL
    files = specs.certificate(spec, v, verdict)
    assert list(files) == [f"aas/files/docs/IC-{SERIAL}.pdf"]
    pdf = files[f"aas/files/docs/IC-{SERIAL}.pdf"]
    assert pdf.startswith(b"%PDF-1.4") and SERIAL.encode() in pdf and b"PO-0042" in pdf
    assert b"NRN-26-33873" in pdf and len(pdf) < 20_000


def test_rejected_part_has_no_certificate_and_an_inactive_passport(specs):
    v = {**PACKED, "deltaE": 40.0, "container": 2}
    verdict = evaluate(v, Limits())
    spec = specs.build(v, "packed", verdict, pcf=3.9)
    documents = _values(spec, "HandoverDocumentation")["Documents"]
    assert [d["DocumentIds"][0]["DocumentIdentifier"] for d in documents] == [
        "DS-PC3280", "OM-PC3280", "RI-PC3280", "SVHC-PC3280"]
    assert specs.certificate(spec, v, verdict) == {}
    assert _values(spec, "DppMetadata")["dppStatus"] == "Inactive"


def test_as_built_bom_mirrors_the_type_bom_with_batch_nodes(specs):
    type_spec = load_assets(DATA_ROOT, {"PC3280_TYPE"})[0]
    type_nodes = passport.values_of(type_spec, "HierarchicalStructures")["EntryNode"]["statements"]["Node"]
    nodes = passport.bom_nodes(specs.build(V, "released"))
    assert [(n["_idShort"], n["statements"]["BulkCount"]) for n in nodes] == [
        (n["_idShort"], n["statements"]["BulkCount"]) for n in type_nodes]
    for node in nodes:  # batches have no AAS: CoManagedEntity, linked to the type node by SameAs
        assert node["entityType"] == "CoManagedEntity" and "globalAssetId" not in node
        assert node["statements"]["SameAs"][0]["second"].endswith(f"#EntryNode.{node['_idShort']}")


def test_blueprint_content_list_matches_the_template_semantic_ids():
    blueprint = load_blueprint()
    assert _values(blueprint, "DppMetadata")["contentSpecificationIds"] == list(passport.CONTENT.values())
    library = BuildContext().library
    for entry in blueprint["submodels"]:
        id_short = entry.get("idShort", entry["template"].split("-")[0])
        if id_short in passport.CONTENT:
            template = library.get(entry["template"])
            assert template["semanticId"]["keys"][0]["value"] == passport.CONTENT[id_short], id_short


def test_pdf_structure_is_consistent():
    page = Page()
    page.text(50, 50, "Leak rate ≤ 1.0 cm³/min (Δ) \\ test")
    pdf = render(page, {"Title": "t"})
    xref = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    assert pdf[xref:xref + 4] == b"xref"
    offsets = [int(o) for o in re.findall(rb"(\d{10}) 00000 n", pdf)]
    assert [pdf[o:o + 8] for o in offsets] == [b"%d 0 obj\n" % (i + 1) for i in range(len(offsets))]
    assert b"<= 1.0 cm\xb3/min \\(Delta \\) \\\\ test" in pdf


def test_certificate_is_deterministic_and_reports_failures():
    assert generate(sample()) == generate(sample())
    data = CertificateData(**{**sample().__dict__, "leak_rate": 1.4})
    assert not data.passed and b"failed" in generate(data)


class _Aas:
    def __init__(self):
        self.attachments, self.submodels = [], []

    def put_concept_description(self, cd):
        pass

    def put_submodel(self, sm):
        self.submodels.append(sm["idShort"])

    def put_shell(self, shell):
        pass

    def put_attachment(self, sm_id, path, data, name, content_type):
        self.attachments.append((path, name, len(data), content_type))


def test_store_uploads_documents_and_the_generated_certificate(specs):
    v = PACKED
    verdict = evaluate(v, Limits())
    spec = specs.build(v, "packed", verdict, pcf=3.9)
    aas = _Aas()
    WorkpieceStore(BuildContext(), aas).publish(spec, {f"aas/files/docs/IC-{SERIAL}.pdf": b"%PDF-cert"})
    by_name = {name: (path, size, ctype) for path, name, size, ctype in aas.attachments}
    first = "Documents[0].DocumentVersions[0].DigitalFiles[0]"
    assert by_name[f"IC-{SERIAL}.pdf"] == (first, 9, "application/pdf")
    assert set(by_name) == {f"IC-{SERIAL}.pdf", "DS-PC3280.pdf", "OM-PC3280.pdf", "RI-PC3280.pdf",
                            "SVHC-PC3280.pdf"}
    assert by_name["SVHC-PC3280.pdf"][0] == "Documents[4].DocumentVersions[0].DigitalFiles[0]"


def test_file_element_paths():
    elements = [{"modelType": "SubmodelElementList", "idShort": "L", "value": [
        {"modelType": "SubmodelElementCollection", "value": [{"modelType": "File", "idShort": "F"}]}]},
        {"modelType": "File", "idShort": "Top"}]
    assert [p for p, _ in file_elements(elements)] == ["L[0].F", "Top"]
