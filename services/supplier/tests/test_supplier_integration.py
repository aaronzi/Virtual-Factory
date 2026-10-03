"""Supplier data exchange against the running stack (`uv run pytest -m integration`, ADR-0028): the supplier
AAS environment (8191) with its preload, a batch AAS published through the ERP goods receipt and resolvable
via federated discovery, packed parts whose PCF uses supplier primary data, and as-built BoM batch nodes that
resolve to the supplier's batch AAS. The last two need parts packed in the current session (run the
factory)."""

from __future__ import annotations

import httpx
import pytest

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.registry import RegistryConfig
from vf_common.resolver import AasResolver

pytestmark = pytest.mark.integration
SUPPLIER_URL, PORTAL, ERP, PCF = ("http://localhost:8191", "http://localhost:8190", "http://localhost:8098",
                                  "http://localhost:8097")
REGISTRIES = {"VF_AAS_URL": "http://localhost:8091",
              "VF_AAS_REGISTRIES": "vf=http://localhost:8091,supplier=http://localhost:8191"}
CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"
AAS_URL = "http://localhost:8091"


@pytest.fixture(scope="module")
def resolver() -> AasResolver:
    try:
        httpx.get(f"{SUPPLIER_URL}/shells", params={"limit": 1}, timeout=5).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("supplier AAS environment not running")
    return AasResolver(RegistryConfig.from_env(REGISTRIES))


@pytest.fixture(scope="module")
def packed() -> dict:
    try:
        recent = httpx.get(f"{PCF}/api/footprints", params={"limit": 50}, timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("sustainability service not running")
    primary = [f for f in recent if any(c.get("dataQuality") == "primary" for c in f["components"])]
    if not primary:
        pytest.skip("no part with supplier batch data packed in the current session (run the factory)")
    return primary[0]


def test_supplier_environment_hosts_companies_and_product_types(resolver):
    shells = BasyxClient(SUPPLIER_URL).list_shells()
    kinds = {s["idShort"]: s["assetInformation"]["assetKind"] for s in shells}
    companies = {"DruckgussPfalz", "DichtungstechnikSued", "NormteileRheinNeckar",
                 "KunststofftechnikWestrich"}
    assert companies <= set(kinds)
    assert sum(k == "Type" for k in kinds.values()) == 5
    # the customer's purchased-part AAS and the supplier's product type describe the same trade item (GTIN)
    both = resolver.lookup(gtin="04099994010016")
    assert ids.aas_id("CMP_PROTECTIVE_CAP") in both and any("/kunststofftechnik-westrich/" in a for a in both)


def test_goods_receipt_publishes_a_batch_aas_resolvable_by_federated_discovery(resolver):
    staged = httpx.post(f"{ERP}/api/material-staging", json={"material": "5032-1009", "lot": "KTW-26-0911"},
                        timeout=60)
    assert staged.status_code in (200, 201), staged.text
    batch = staged.json()["SupplierBatch"]
    assert batch["DespatchAdviceNumber"] == "DA-KTW-26-0911"
    shell = resolver.resolve_asset(batch["GlobalAssetId"])
    assert shell.environment == "supplier" and shell.aas_id == batch["AasId"]
    cf = resolver.submodel_of(shell.aas_id, semantic_id=CARBON_FOOTPRINT)
    total = resolver.repository(cf).get_value(cf.id, "ProductCarbonFootprints[0].PcfCO2eq")
    assert float(total) == pytest.approx(batch["PcfCO2eqPerPiece"])
    certificate = httpx.get(batch["MaterialCertificate"]["Href"], timeout=10)
    assert certificate.status_code == 200 and certificate.content.startswith(b"%PDF")


def test_packed_part_uses_supplier_primary_data(packed):
    primary = [c for c in packed["components"] if c["dataQuality"] == "primary"]
    for component in primary:
        assert component["source"] == "supplier-batch"
        assert component["assetId"].endswith("/10/" + component["batch"])
    assert packed["supplierSpecificShareA1"] > 0 and packed["primaryDataShare"] > 0
    tag = "WP_" + packed["serial"].replace("-", "_")
    sm_id = ids.submodel_id(tag, "CarbonFootprint", "1")
    share = BasyxClient(AAS_URL).get_value(sm_id, "ProductCarbonFootprints[1].SupplierSpecificDataShare")
    assert float(share) == pytest.approx(packed["supplierSpecificShareA1"], abs=0.1)


def test_bom_batch_node_resolves_to_the_supplier_batch_aas(packed, resolver):
    tag = "WP_" + packed["serial"].replace("-", "_")
    bom = BasyxClient(AAS_URL).get_submodel(ids.submodel_id(tag, "HierarchicalStructures", "1"))
    entry = next(e for e in bom["submodelElements"] if e["idShort"] == "EntryNode")
    nodes = [n for n in entry["statements"] if n.get("entityType") == "SelfManagedEntity"]
    assert len(nodes) == 5
    resolved = 0
    for node in nodes:
        lot = next(s["value"] for s in node["statements"] if s["idShort"] == "BatchId")
        shell = resolver.resolve_asset(node["globalAssetId"])
        info = resolver.submodel_of(shell.aas_id, "BatchInformation")
        assert shell.environment == "supplier"
        assert resolver.repository(info).get_value(info.id, "BatchId") == lot
        resolved += 1
    assert resolved == 5
