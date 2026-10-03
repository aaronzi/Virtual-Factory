"""Against the running compose stack (`uv run pytest -m integration`): a produced part is resolved from its
GS1 Digital Link through discovery -> registry -> repository, and the resolver service (8096) answers with
redirect, linkset and passport page. Needs at least one produced workpiece (run the factory for ~30 s)."""

from __future__ import annotations

import os

import httpx
import pytest

from vf_common.basyx import BasyxClient
from vf_common.digital_link import parse
from vf_common.registry import RegistryConfig
from vf_common.registry_aas import RegistryAas
from vf_common.resolver import AasResolver

pytestmark = pytest.mark.integration
AAS_URL = "http://localhost:8091"
RESOLVER_URL = os.environ.get("VF_RESOLVER_TEST_URL", "http://localhost:8096")


@pytest.fixture(scope="module")
def part_link() -> str:
    try:
        shells = BasyxClient(AAS_URL).list_shells()
    except httpx.HTTPError:
        pytest.skip("compose stack not running")
    links = [s["assetInformation"].get("globalAssetId", "") for s in shells if "/ids/aas/WP_" in s["id"]]
    links = [g for g in links if "/21/" in g]
    if not links:
        pytest.skip("no workpiece produced yet")
    return links[-1]


def test_part_resolves_via_discovery_registry_and_repository(part_link):
    resolver = AasResolver(RegistryConfig.from_env({"VF_AAS_URL": AAS_URL}))
    shell = resolver.resolve_asset(part_link)
    serial = parse(part_link).serial
    assert shell.aas_id.endswith("/WP_" + serial.replace("-", "_"))
    assert resolver.lookup(serialNumber=serial) == [shell.aas_id]
    nameplate = resolver.submodel_of(shell.aas_id, "Nameplate")
    aas = RegistryAas(resolver)
    assert aas.get_value(nameplate.id, "SerialNumber") == serial
    assert aas.get_shell(shell.aas_id)["assetInformation"]["globalAssetId"] == part_link


def test_device_submodel_by_asset_id():
    resolver = AasResolver(RegistryConfig.from_env({"VF_AAS_URL": AAS_URL}))
    try:
        line_control = resolver.submodel_of_asset("https://virtual-factory.example/ids/asset/LINE01",
                                                  "LineControl")
    except httpx.HTTPError:
        pytest.skip("compose stack not running")
    assert line_control.href.startswith("http://localhost:8091/submodels/")


@pytest.fixture(scope="module")
def service():
    try:
        httpx.get(f"{RESOLVER_URL}/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("resolver service not running")
    return httpx.Client(base_url=RESOLVER_URL, timeout=10)


def test_resolver_redirects_and_serves_linkset_and_page(service, part_link):
    path = parse(part_link).path
    redirect = service.get(path)
    assert redirect.status_code == 307 and "/passport" + path in redirect.headers["location"]
    linkset = service.get(path, headers={"Accept": "application/linkset+json"}).json()["linkset"][0]
    assert linkset["anchor"] == part_link
    assert {"https://gs1.org/voc/pip", "https://virtual-factory.example/voc/dpp",
            "https://virtual-factory.example/voc/aas"} <= set(linkset)
    page = service.get("/passport" + path, headers={"Accept-Language": "de"})
    assert page.status_code == 200 and "Digitaler Produktpass" in page.text
    assert parse(part_link).serial in page.text
    dpp = service.get(path, params={"linkType": "vf:dpp"}).headers["location"]
    assert dpp.startswith("http://localhost:8093/v1/dppsByProductId/")
    assert service.get("/01/04099999032808/21/UNKNOWN").status_code == 404
