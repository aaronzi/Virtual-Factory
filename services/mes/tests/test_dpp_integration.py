"""Item-level passports through the BaSyx Go DPP API (ADR-0021) against the running stack
(`uv run pytest -m integration`). Needs produced parts: the factory (Godot) must have packed at least one good
part, otherwise the item tests are skipped; the retention test needs a shipped part of an earlier session."""

from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest

from mes.passport import CONTENT
from vf_common.basyx import BasyxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

pytestmark = pytest.mark.integration
AAS_URL, DPP_URL = "http://localhost:8091", "http://localhost:8093"
TYPE_PRODUCT_ID = "https://virtual-factory.example/01/04099999032808"
DPP_METADATA = "https://admin-shell.io/idta/cds/dppMetadata/1"


def _get(path: str, **params) -> httpx.Response:
    return httpx.get(f"{DPP_URL}{path}", params=params, timeout=10)


def _enc(identifier: str) -> str:
    return quote(identifier, safe="")


@pytest.fixture(scope="module")
def passport() -> dict:
    """The newest packed good part's passport (read by DPP id = AAS id)."""
    try:
        assert _get("/health").status_code == 200
        shells = BasyxClient(AAS_URL).list_shells()
    except (httpx.HTTPError, AssertionError):
        pytest.skip("compose stack with dpp-api not running")
    workpieces = sorted((s["id"] for s in shells if "/aas/WP_" in s["id"]), reverse=True)
    for aas_id in workpieces:
        response = _get(f"/v1/dpps/{_enc(aas_id)}")
        if response.status_code == 200 and CONTENT["HandoverDocumentation"] in response.json():
            doc = response.json()
            if doc["dppStatus"] == "Active":
                return doc
    pytest.skip("no packed good part yet (run the factory)")


def test_passport_by_dpp_id_is_item_level_and_complete(passport):
    assert passport["granularity"] == "Item"
    assert passport["contentSpecificationIds"] == list(CONTENT.values())
    for semantic_id in CONTENT.values():
        assert semantic_id in passport, f"content section {semantic_id} missing"
    shell = BasyxClient(AAS_URL).get_shell(passport["digitalProductPassportId"])
    assert shell["assetInformation"]["globalAssetId"] == passport["uniqueProductIdentifier"]


def test_passport_by_product_id_is_the_same(passport):
    response = _get(f"/v1/dppsByProductId/{_enc(passport['uniqueProductIdentifier'])}")
    assert response.status_code == 200
    assert response.json()["digitalProductPassportId"] == passport["digitalProductPassportId"]


def test_element_read_and_lots(passport):
    serial = passport["uniqueProductIdentifier"].rsplit("/", 1)[-1]
    path = f"$['{CONTENT['Nameplate']}']['SerialNumber']"
    response = _get(f"/v1/dpps/{_enc(passport['digitalProductPassportId'])}/elements/{_enc(path)}")
    assert response.status_code == 200 and response.json() == serial
    nodes = passport[CONTENT["HierarchicalStructures"]]["EntryNode"]["statements"]
    lots = {name: n["statements"]["BatchId"] for name, n in nodes.items()
            if "BatchId" in n.get("statements", {})}
    assert len(lots) == 9 and all(lots.values())


def test_certificate_attachment_is_downloadable(passport):
    documents = passport[CONTENT["HandoverDocumentation"]]["Documents"]
    certificate = documents[0]["DocumentVersions"][0]["DigitalFiles"][0]
    url = certificate if isinstance(certificate, str) else certificate.get("url") or certificate.get("value")
    assert url.startswith(f"{AAS_URL}/submodels/"), url
    pdf = httpx.get(url, timeout=10)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) < 20_000
    assert len(documents) == 5


def test_model_level_passport_of_the_type():
    try:
        response = _get(f"/v1/dppsByProductId/{_enc(TYPE_PRODUCT_ID)}")
    except httpx.HTTPError:
        pytest.skip("dpp-api not running")
    assert response.status_code == 200
    doc = response.json()
    assert doc["granularity"] == "Model" and doc["digitalProductPassportId"].endswith("/aas/PC3280_TYPE")
    by_id = _get(f"/v1/dpps/{_enc(doc['digitalProductPassportId'])}")
    assert by_id.status_code == 200 and CONTENT["ContactInformations"] in by_id.json()



def test_shipped_passports_of_earlier_sessions_are_still_served():
    """Retention (ADR-0025): passports of shipped parts survive new sessions; their last update lies before
    the start of the current session (retained session birth on the UNS)."""
    started = _session_start()
    try:
        metadata = BasyxClient(AAS_URL).list_submodels(semantic_id=DPP_METADATA, semantic_key_type="Submodel")
    except httpx.HTTPError:
        pytest.skip("compose stack not running")
    earlier = []
    for sm in metadata:
        values = {e["idShort"]: e.get("value") for e in sm.get("submodelElements", [])}
        shipped = values.get("dppStatus") == "Active"
        if "/sm/WP_" in sm["id"] and shipped and values.get("lastUpdate", "") < started:
            earlier.append(sm["id"].split("/")[5])
    if not earlier:
        pytest.skip("no shipped part from an earlier session (run two factory sessions)")
    response = _get(f"/v1/dpps/{_enc('https://virtual-factory.example/ids/aas/' + earlier[-1])}")
    assert response.status_code == 200 and response.json()["dppStatus"] == "Active"


def _session_start() -> str:
    uns, client = Uns.load(), MqttClient("vf-test-dpp", "localhost", 1883)
    client.subscribe(uns.session_topic, qos=1)
    if not client.start(5):
        pytest.skip("MQTT broker not reachable")
    birth = client.get(timeout=3)
    client.stop()
    started = (birth.json() or {}).get("started") if birth else None
    if not started:
        pytest.skip("no factory session yet")
    return started
