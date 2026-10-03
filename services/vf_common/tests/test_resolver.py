"""Discovery -> registry -> repository resolution against a fake AAS infrastructure (httpx.MockTransport)."""

import base64
import json

import httpx
import pytest

from vf_common.basyx import b64
from vf_common.registry import RegistryConfig, parse_environments, repository_base
from vf_common.registry_aas import RegistryAas
from vf_common.resolver import AasResolver, NotResolved

DL = "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000001"
AAS = "urn:aas:wp1"
SM = "urn:sm:wp1:nameplate"
SUPPLIER_AAS, SUPPLIER_SM = "urn:aas:valve", "urn:sm:valve:nameplate"


def _decode(value: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


class FakeInfra:
    """Two BaSyx-like environments: own (http://own) and a supplier's (http://sup)."""

    def __init__(self):
        self.calls: list[str] = []
        self.links = {"http://own": {("globalAssetId", DL): AAS, ("serialNumber", "PC3280-2026-000001"): AAS},
                      "http://sup": {("serialNumber", "V-1"): SUPPLIER_AAS}}
        self.shells = {"http://own": {AAS: [SM]}, "http://sup": {SUPPLIER_AAS: [SUPPLIER_SM]}}
        self.submodels = {"http://own": {SM: ("Nameplate", "urn:sem:nameplate")},
                          "http://sup": {SUPPLIER_SM: ("Nameplate", "urn:sem:nameplate")}}

    down: set[str] = set()  # hosts that do not answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.host}{request.url.path}")
        if request.url.host in self.down:
            raise httpx.ConnectError("connection refused", request=request)
        base = f"http://{request.url.host}"
        public = base.replace("http://", "http://public-")
        path = request.url.path
        if path == "/lookup/shells":
            wanted = [_decode(v) for v in request.url.params.get_list("assetIds")]
            hits = {self.links[base].get((w["name"], w["value"])) for w in wanted}
            return httpx.Response(200, json={"result": [h for h in hits if h] if len(hits) == 1 else []})
        if path.startswith("/shell-descriptors/"):
            aas = _id(path)
            if aas not in self.shells[base]:
                return httpx.Response(404)
            return httpx.Response(200, json={
                "id": aas, "endpoints": [_ep("AAS-3.0", f"{public}/shells/{b64(aas)}")],
                "submodelDescriptors": [{"id": s} for s in self.shells[base][aas]]})
        if path.startswith("/submodel-descriptors"):
            return self._submodel_descriptors(base, public, path)
        if path.startswith("/submodels/") or path.startswith("/shells/"):
            return httpx.Response(200, json={"id": _id(path), "served_by": base})
        return httpx.Response(404)

    def _submodel_descriptors(self, base: str, public: str, path: str) -> httpx.Response:
        def descriptor(sm):
            id_short, sem = self.submodels[base][sm]
            return {"id": sm, "idShort": id_short,
                    "endpoints": [_ep("SUBMODEL-3.0", f"{public}/submodels/{b64(sm)}")],
                    "semanticId": {"type": "ExternalReference",
                                   "keys": [{"type": "GlobalReference", "value": sem}]}}
        if path == "/submodel-descriptors":
            return httpx.Response(200, json={"result": [descriptor(s) for s in self.submodels[base]]})
        sm = _id(path)
        return httpx.Response(200, json=descriptor(sm)) if sm in self.submodels[base] else httpx.Response(404)


def _ep(interface, href):
    return {"interface": interface, "protocolInformation": {"href": href, "endpointProtocol": "http"}}


def _id(path: str) -> str:
    encoded = path.rstrip("/").rsplit("/", 1)[1]
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()


@pytest.fixture
def setup():
    infra = FakeInfra()
    config = RegistryConfig(parse_environments("own=http://own,supplier=http://sup"),
                            {"http://public-own": "http://own", "http://public-sup": "http://sup"},
                            cache_ttl_s=60)
    now = [0.0]
    client = httpx.Client(transport=httpx.MockTransport(infra))
    resolver = AasResolver(config, client=client, clock=lambda: now[0])
    resolver.repository = _patched_repository(resolver, infra)
    return infra, resolver, now


def _patched_repository(resolver, infra):
    original = resolver.repository

    def repository(endpoint):
        repo = original(endpoint)
        repo.http = httpx.Client(base_url=repo.base_url, transport=httpx.MockTransport(infra))
        return repo
    return repository


def test_asset_id_resolves_through_discovery_and_registry(setup):
    infra, resolver, _ = setup
    shell = resolver.resolve_asset(DL)
    assert shell.aas_id == AAS and shell.environment == "own" and shell.submodel_ids == [SM]
    nameplate = resolver.submodel_of(AAS, "Nameplate")
    assert nameplate.id == SM and nameplate.semantic_id == "urn:sem:nameplate"
    assert resolver.lookup(serialNumber="PC3280-2026-000001") == [AAS]


def test_federated_environment_is_searched_and_endpoints_are_rewritten(setup):
    infra, resolver, _ = setup
    shell = resolver.resolve_asset(serialNumber="V-1")
    assert shell.environment == "supplier" and shell.href.startswith("http://public-sup/shells/")
    assert resolver.repository(shell).base_url == "http://sup"
    aas = RegistryAas(resolver)
    assert aas.get_submodel(SUPPLIER_SM)["served_by"] == "http://sup"
    assert aas.get_submodel(SM)["served_by"] == "http://own"
    assert {s["id"] for s in aas.list_submodels("urn:sem:nameplate")} == {SM, SUPPLIER_SM}


def test_results_are_cached_until_ttl_or_change_event(setup):
    infra, resolver, now = setup
    resolver.shell(AAS)
    resolver.shell(AAS)
    assert sum(c.endswith(f"/shell-descriptors/{b64(AAS)}") for c in infra.calls) == 1
    resolver.on_event("vf/basyx/submodelrepository/submodel/updated", json.dumps({"subject": SM}).encode())
    resolver.on_event("vf/basyx/aasrepository/shell/updated", json.dumps({"subject": AAS}).encode())
    resolver.shell(AAS)
    assert sum(c.endswith(f"/shell-descriptors/{b64(AAS)}") for c in infra.calls) == 2
    now[0] = 61.0
    resolver.shell(AAS)
    assert sum(c.endswith(f"/shell-descriptors/{b64(AAS)}") for c in infra.calls) == 3


def test_unknown_ids_raise_not_resolved_and_are_not_cached(setup):
    infra, resolver, _ = setup
    with pytest.raises(NotResolved):
        resolver.resolve_asset("https://virtual-factory.example/01/04099999032808/21/NOPE")
    with pytest.raises(NotResolved):
        resolver.submodel_of(AAS, "Missing")
    assert RegistryAas(resolver).get_shell("urn:aas:none") is None


def test_configuration_from_environment_variables():
    config = RegistryConfig.from_env({"VF_AAS_URL": "http://aas-env:8091",
                                      "VF_AAS_PUBLIC_URL": "http://localhost:8091"})
    assert [e.name for e in config.environments] == ["vf"]
    assert config.reachable("http://localhost:8091/shells/x") == "http://aas-env:8091/shells/x"
    federated = RegistryConfig.from_env({"VF_AAS_REGISTRIES": json.dumps([
        {"name": "sup", "discovery": "http://d", "aas_registry": "http://r/",
         "submodel_registry": "http://s"}])})
    assert federated.environments[0].aas_registry == "http://r" and federated.endpoint_map == {}
    assert repository_base("http://h:1/api/submodels/abc") == "http://h:1/api"


def test_an_unreachable_environment_is_skipped_but_never_taken_as_unknown(setup):
    infra, resolver, _ = setup
    infra.down = {"sup"}
    assert resolver.resolve_asset(DL).environment == "own"  # the own environment answers
    assert resolver.lookup(DL) == [AAS]
    with pytest.raises(httpx.ConnectError):  # only the supplier knows it: retry later, not "no AAS"
        resolver.resolve_asset(serialNumber="V-1")
    assert [s.id for s in resolver.find_submodels("urn:sem:nameplate")] == [SM]  # partial result
    infra.down = {"own", "sup"}
    with pytest.raises(httpx.ConnectError):
        resolver.shell("urn:aas:other")
