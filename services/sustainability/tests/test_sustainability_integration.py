"""PCF written by the sustainability service, against the running stack (`uv run pytest -m integration`):
the newest footprint of the current session is in the CarbonFootprint submodel of the workpiece AAS (owned
by the sustainability service, referenced from the shell the MES created) and in its passport. Skipped
without packed parts in the current session."""

from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest

from vf_common import ids
from vf_common.basyx import BasyxClient

pytestmark = pytest.mark.integration
API, AAS_URL, DPP_URL = "http://localhost:8097", "http://localhost:8091", "http://localhost:8093"
CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"


@pytest.fixture(scope="module")
def footprint() -> dict:
    try:
        recent = httpx.get(f"{API}/api/footprints", params={"limit": 5}, timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("sustainability service not running")
    if not recent:
        pytest.skip("no part packed in the current session (run the factory)")
    return recent[0]


def test_carbon_footprint_submodel_written_by_the_service(footprint):
    tag = "WP_" + footprint["serial"].replace("-", "_")
    aas = BasyxClient(AAS_URL)
    sm_id = ids.submodel_id(tag, "CarbonFootprint", "1")
    shell = aas.get_shell(ids.aas_id(tag))
    assert sm_id in {r["keys"][0]["value"] for r in shell["submodels"]}
    total = aas.get_value(sm_id, "ProductCarbonFootprints[0].PcfCO2eq")
    assert float(total) == pytest.approx(footprint["total"], abs=1e-4)
    assert footprint["total"] > footprint["material"] > 0 and footprint["method"] in ("historian", "fallback")
    assert all(c["batch"] and c["source"] for c in footprint["components"])


def test_passport_lists_and_serves_the_footprint(footprint):
    tag = "WP_" + footprint["serial"].replace("-", "_")
    response = httpx.get(f"{DPP_URL}/v1/dpps/{quote(ids.aas_id(tag), safe='')}", timeout=10)
    assert response.status_code == 200
    doc = response.json()
    assert CARBON_FOOTPRINT in doc["contentSpecificationIds"] and CARBON_FOOTPRINT in doc
    assert doc["dppStatus"] == ("Inactive" if footprint["rejected"] else "Active")


def test_sustainability_kpis():
    try:
        kpis = httpx.get(f"{API}/api/kpis", timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("sustainability service not running")
    assert {"session", "goodParts", "avgPcfGoodPart", "energyPerGoodPartKWh", "line"} <= set(kpis)
