"""Secure profile against the running SECURE compose stack (ADR-0027), with real Keycloak tokens:

    docker compose -f infra/docker-compose.yml -f infra/docker-compose.secure.yml up -d --build
    uv run pytest -m secure

Skipped unless Keycloak (8180) serves the realm and the AAS environment refuses anonymous writes."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

import httpx
import paho.mqtt.client as paho
import pytest

from vf_common.basyx import b64

pytestmark = pytest.mark.secure
REALM = "http://localhost:8180/realms/virtual-factory"
TOKEN_URL = REALM + "/protocol/openid-connect/token"
AAS, DPP, GRAFANA, RESOLVER = "http://localhost:8091", "http://localhost:8093", "http://localhost:3002", \
    "http://localhost:8096"
IDS = "https://virtual-factory.example/ids"
TYPE_LINK = "https://virtual-factory.example/01/04099999032808"
ROOT = "vf/plant01/final-assembly/line01"
MATERIAL = "https://virtual-factory.example/ids/smt/ProductMaterialComposition/1/0/Submodel"
NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"


@pytest.fixture(scope="module", autouse=True)
def secure_stack():
    try:
        httpx.get(REALM, timeout=3).raise_for_status()
        refused = httpx.post(AAS + "/concept-descriptions", json={}, timeout=5).status_code in (401, 403)
    except httpx.HTTPError:
        pytest.skip("secure compose stack not running (Keycloak 8180)")
    if not refused:
        pytest.skip("AAS environment accepts anonymous writes: the open profile is running")


def user(name: str) -> dict:
    r = httpx.post(TOKEN_URL, data={"grant_type": "password", "client_id": "vf-godot", "username": name,
                                    "password": "virtualfactory"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def service(name: str) -> dict:
    r = httpx.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": f"vf-{name}",
                                    "client_secret": f"vf-{name}-local-secret"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _submodel(tag: str, id_short: str) -> dict:
    return {"modelType": "Submodel", "id": f"{IDS}/sm/{tag}/{id_short}/1", "idShort": id_short,
            "submodelElements": [{"modelType": "Property", "idShort": "Note", "valueType": "xs:string",
                                  "value": "secure profile test"}]}


def _put(body: dict, headers: dict | None) -> int:
    return httpx.put(f"{AAS}/submodels/{b64(body['id'])}", json=body, headers=headers or {}).status_code


def test_anonymous_cannot_write_and_reads_only_public_submodels():
    assert _put(_submodel("WP_SECTEST_0", "Nameplate"), None) in (401, 403)
    listed = httpx.get(AAS + "/submodels", params={"limit": 1000}).json()["result"]
    public = {"Nameplate", "ContactInformations", "CarbonFootprint", "ProductCircularity",
              "HandoverDocumentation", "DppMetadata"}
    assert listed and {s["idShort"] for s in listed} <= public
    assert httpx.get(AAS + "/shells").status_code == 403


def test_mes_writes_workpiece_submodels_but_not_the_carbon_footprint():
    mes, sustainability = service("mes"), service("sustainability")
    plate, pcf = _submodel("WP_SECTEST_1", "Nameplate"), _submodel("WP_SECTEST_1", "CarbonFootprint")
    try:
        assert _put(plate, mes) in (201, 204)
        assert _put(pcf, mes) == 403
        assert _put(pcf, sustainability) in (201, 204)
        assert _put(plate, sustainability) == 403
        assert _put(_submodel("AC01", "Nameplate"), mes) == 403, "device data are not the MES's"
    finally:
        for body in (plate, pcf):
            httpx.delete(f"{AAS}/submodels/{b64(body['id'])}", headers=mes)


def test_bridge_writes_operational_data_only():
    bridge, sm = service("bridge"), b64(f"{IDS}/sm/CV01/OperationalData/1")
    url = f"{AAS}/submodels/{sm}/submodel-elements/OperatingHours/$value"
    value = httpx.get(url, headers=bridge).json()
    assert httpx.patch(url, json=str(value), headers=bridge).status_code == 204
    assert httpx.patch(url, json=str(value), headers=service("mes")).status_code >= 400  # BaSyx: 500 (O58)


def _passport(headers: dict | None) -> dict:
    r = httpx.get(f"{DPP}/v1/dppsByProductId/{quote(TYPE_LINK, safe='')}", headers=headers or {})
    assert r.status_code == 200, r.text[:200]
    return r.json()


def test_passport_sections_depend_on_the_role():
    public = _passport(None)
    assert NAMEPLATE in public and MATERIAL not in public and MATERIAL in public["contentSpecificationIds"]
    assert MATERIAL in _passport(user("recycler1"))
    assert MATERIAL in _passport(user("auditor1"))


def test_line_control_invoke_needs_a_commander_role_and_reaches_the_gateway():
    sm = b64(IDS + "/sm/LINE01/LineControl/1")
    url = f"{AAS}/submodels/{sm}/submodel-elements/ExecutePackMLCommand/invoke"
    command = {"modelType": "Property", "idShort": "Command", "valueType": "xs:string", "value": "Jump"}
    body = {"inputArguments": [{"value": command}], "clientTimeoutDuration": "PT10S"}
    assert httpx.post(url, json=body, headers=user("quality1"), timeout=20).status_code == 403
    ok = httpx.post(url, json=body, headers=user("operator1"), timeout=20)
    # the gateway validated the forwarded token (and answers Accepted=false for "Jump")
    assert ok.status_code == 200, ok.text[:300]
    assert httpx.post("http://localhost:8095/operations/ExecutePackMLCommand", json=[]).status_code == 401


def _mqtt(account: str, received: list | None = None) -> paho.Client:
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=f"test-{account}-{time.time_ns()}")
    client.username_pw_set(account, f"{account}-local-secret")
    if received is not None:
        client.on_message = lambda c, u, m: received.append(m.payload.decode())
    client.connect("localhost", 1883)
    client.loop_start()
    time.sleep(0.5)
    return client


def test_only_the_ops_gateway_account_publishes_commands():
    rc = []
    anonymous = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="test-anon")
    anonymous.on_connect = lambda c, u, f, r, p: rc.append(r.is_failure)
    anonymous.connect("localhost", 1883)
    anonymous.loop_start()
    time.sleep(0.5)
    anonymous.loop_stop()
    assert rc == [True], "anonymous connect refused"
    received: list[str] = []
    listener = _mqtt("explorer", received)
    topic = f"{ROOT}/sectest/cmd/noop"
    listener.subscribe(topic, 1)
    time.sleep(0.3)
    for account in ("historian", "godot", "ops-gateway"):
        sender = _mqtt(account)
        sender.publish(topic, account, qos=1).wait_for_publish(3)
        sender.disconnect()
    time.sleep(0.5)
    listener.disconnect()
    assert received == ["ops-gateway"]


def test_opcua_refuses_anonymous_and_unencrypted_sessions():
    from asyncua import Client

    from vf_common.opcua_security import OpcUaSecurity, secure_client

    async def attempt(security: OpcUaSecurity | None) -> bool:
        client = Client("opc.tcp://localhost:4840/vf/plc01", timeout=5)
        try:
            if security:
                await secure_client(client, security, "secure-test")
            await client.connect()
            await client.disconnect()
            return True
        except Exception:  # noqa: BLE001 - any refusal counts
            return False

    assert not asyncio.run(attempt(None)), "SecurityPolicy None / anonymous"
    assert not asyncio.run(attempt(OpcUaSecurity(mode="sign_encrypt"))), "anonymous user token"
    assert asyncio.run(attempt(OpcUaSecurity(mode="sign_encrypt", user="explorer",
                                             password="explorer-local-secret")))


def test_grafana_requires_login():
    assert httpx.get(GRAFANA + "/api/health").status_code == 200
    assert httpx.get(GRAFANA + "/api/dashboards/uid/vf-line01-live").status_code == 401
    login = httpx.get(GRAFANA + "/login/generic_oauth", follow_redirects=False)
    assert login.status_code == 302 and login.headers["location"].startswith(REALM)


def test_service_apis_and_resolver_links_need_tokens():
    assert httpx.get("http://localhost:8099/api/alarms").status_code == 401
    assert httpx.get("http://localhost:8099/api/alarms", headers=user("operator1")).status_code == 200
    order = {"material": "PC3280", "quantity": 1}
    created = httpx.post("http://localhost:8098/api/orders", json=order, headers=user("operator1"))
    assert created.status_code == 403
    link = f"{RESOLVER}/01/04099999032808"
    refused = httpx.get(link, params={"linkType": "vf:aas"}, follow_redirects=False)
    assert refused.status_code == 401 and refused.json()["login"]["token_endpoint"] == TOKEN_URL
    allowed = httpx.get(link, params={"linkType": "vf:aas"}, headers=user("auditor1"), follow_redirects=False)
    assert allowed.status_code == 307
    page = httpx.get(f"{RESOLVER}/passport/01/04099999032808").text
    assert "For authorised parties only" in page and "Material composition" in page


def _grafana_login(name: str) -> httpx.Response:
    """Browser-like authorization code flow (Grafana → Keycloak login form → Grafana session)."""
    import html
    import re
    client = httpx.Client(follow_redirects=True, timeout=20)
    form = client.get(GRAFANA + "/login/generic_oauth")
    for cookie in client.cookies.jar:
        cookie.secure = False  # Keycloak's cookies are Secure; browsers send them to http://localhost too
    action = html.unescape(re.search(r'action="([^"]+)"', form.text).group(1))
    client.post(action, data={"username": name, "password": "virtualfactory", "credentialId": ""})
    return client.get(GRAFANA + "/api/user/orgs")


def test_grafana_maps_realm_roles_and_refuses_unmapped_users():
    assert _grafana_login("operator1").json()[0]["role"] == "Viewer"
    assert _grafana_login("planner1").json()[0]["role"] == "Editor"
    assert _grafana_login("recycler1").status_code == 401
