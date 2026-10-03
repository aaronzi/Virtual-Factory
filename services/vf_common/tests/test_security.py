"""Secure profile (ADR-0027): client-credentials token helper, bearer token validation, HTTP API guard,
MQTT / BPMN / OPC UA credentials from the environment."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from vf_common.testing_tokens import AUDIENCE, ISSUER, token, verifier
from vf_common.auth import ClientCredentials, TokenError, bpmn_auth, mqtt_credentials, service_auth
from vf_common.http_api import Guard, Router
from vf_common.jwt_auth import InvalidToken, JwtVerifier, bearer, verifier_from_env
from vf_common.opcua_security import AccountManager, OpcUaSecurity, RoleRuleset

TOKEN_URL = "http://keycloak:8080/realms/virtual-factory/protocol/openid-connect/token"


class FakeIdp:
    """Token endpoint: counts grants, issues tokens valid for `lifetime` seconds."""

    def __init__(self, lifetime: int = 300, status: int = 200):
        self.lifetime, self.status, self.grants = lifetime, status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=") for x in request.content.decode().split("&"))
        self.grants.append(form)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "unauthorized_client"})
        return httpx.Response(200, json={"access_token": f"tok-{len(self.grants)}",
                                         "expires_in": self.lifetime})


def test_client_credentials_are_cached_until_shortly_before_expiry():
    idp, now = FakeIdp(lifetime=300), [0.0]
    auth = ClientCredentials(TOKEN_URL, "vf-mes", "s3cret", clock=lambda: now[0],
                             transport=httpx.MockTransport(idp))
    assert auth.token() == "tok-1" and auth.token() == "tok-1"
    assert idp.grants[0] == {"grant_type": "client_credentials", "client_id": "vf-mes",
                             "client_secret": "s3cret"}
    now[0] = 269.0  # 300 s lifetime - 30 s skew
    assert auth.token() == "tok-1"
    now[0] = 271.0
    assert auth.token() == "tok-2"


def test_request_is_retried_once_with_a_fresh_token_after_401():
    idp = FakeIdp()
    auth = ClientCredentials(TOKEN_URL, "vf-mes", "s", transport=httpx.MockTransport(idp))
    seen = []

    def api(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(401 if len(seen) == 1 else 200, json={})

    with httpx.Client(transport=httpx.MockTransport(api), auth=auth) as client:
        assert client.get("http://aas-env:8091/shells").status_code == 200
    assert seen == ["Bearer tok-1", "Bearer tok-2"]


def test_refused_client_raises_token_error():
    auth = ClientCredentials(TOKEN_URL, "vf-mes", "wrong", transport=httpx.MockTransport(FakeIdp(status=401)))
    with pytest.raises(TokenError, match="refused"):
        auth.token()


def test_environment_switches_credentials_on_only_in_the_secure_profile():
    assert service_auth({}) is None and bpmn_auth({}) is None and mqtt_credentials({}) is None
    env = {"VF_OIDC_TOKEN_URL": TOKEN_URL, "VF_OIDC_CLIENT_ID": "vf-bridge", "VF_OIDC_CLIENT_SECRET": "x",
           "VF_BPMN_USER": "mes", "VF_BPMN_PASSWORD": "p", "VF_MQTT_USER": "bridge", "VF_MQTT_PASSWORD": "q"}
    assert service_auth(env) is service_auth(env)  # one shared token cache per client
    assert service_auth(env).client_id == "vf-bridge"
    assert isinstance(bpmn_auth(env), httpx.BasicAuth)
    assert mqtt_credentials(env) == ("bridge", "q")


def test_valid_token_yields_principal_with_realm_roles():
    caller = verifier().verify(token(["operator", "default-roles-virtual-factory"]))
    assert caller.name == "operator1" and caller.has_any(["operator"]) and not caller.has_any(["planner"])


@pytest.mark.parametrize("bad, reason", [
    (lambda: token(["operator"], exp=int(time.time()) - 120), "expired"),
    (lambda: token(["operator"], iss="http://evil/realms/x"), "issuer"),
    (lambda: token(["operator"], aud="account"), "not issued"),
    (lambda: token(["operator"], key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
     "signature"),
    (lambda: token(["operator"], kid="other"), "unknown signing key"),
    (lambda: "abc.def", "malformed"),
])
def test_invalid_tokens_are_rejected(bad, reason):
    with pytest.raises(InvalidToken, match=reason):
        verifier().verify(bad())


def test_unknown_key_id_refetches_the_jwks_once_per_miss():
    calls = []
    v = JwtVerifier(ISSUER, "u", AUDIENCE, fetch=lambda url: calls.append(url) or {"keys": []})
    with pytest.raises(InvalidToken):
        v.verify(token(["x"]))
    assert calls == ["u"]


def test_bearer_header_parsing_and_verifier_from_env():
    assert bearer("Bearer abc") == "abc"
    with pytest.raises(InvalidToken):
        bearer("Basic abc")
    assert verifier_from_env({}) is None
    v = verifier_from_env({"VF_OIDC_ISSUER": ISSUER, "VF_OIDC_AUDIENCE": AUDIENCE})
    assert v.jwks_url == ISSUER + "/protocol/openid-connect/certs" and v.audience == AUDIENCE


def _router(guard: Guard | None) -> Router:
    router = Router(guard)
    router.add("GET", "/health", lambda q: {"ok": True}, public=True)
    router.add("GET", "/api/items", lambda q: {"caller": q.principal.name if q.principal else None})
    router.add("POST", "/api/items", lambda q: {"done": True}, ("planner",))
    return router


def test_router_without_guard_checks_nothing():
    router = _router(None)
    assert router.dispatch("POST", "/api/items").status == 200
    assert router.dispatch("GET", "/api/items").body == {"caller": None}


def test_router_with_guard_requires_token_and_role():
    router = _router(Guard(verifier()))
    assert router.dispatch("GET", "/health").status == 200
    assert router.dispatch("GET", "/api/items").status == 401
    assert router.dispatch("GET", "/api/items", authorization="Bearer x.y.z").status == 401
    reply = router.dispatch("GET", "/api/items", authorization="Bearer " + token(["operator"]))
    assert reply.status == 200 and reply.body == {"caller": "operator1"}
    assert router.dispatch("POST", "/api/items", b"{}", "Bearer " + token(["operator"])).status == 403
    planner = "Bearer " + token(["planner"], "planner1")
    assert router.dispatch("POST", "/api/items", b"{}", planner).status == 200


def test_opcua_accounts_and_method_permissions():
    security = OpcUaSecurity.from_env({"VF_OPCUA_SECURITY": "sign_encrypt",
                                       "VF_OPCUA_USERS": "edge:pw:operate, explorer:x:read"})
    assert security.secure and security.accounts == {"edge": ("pw", "operate"), "explorer": ("x", "read")}
    users = AccountManager(security.accounts)
    assert users.get_user(None) is None, "anonymous refused"
    assert users.get_user(None, "edge", "wrong") is None
    edge, explorer = users.get_user(None, "edge", "pw"), users.get_user(None, "explorer", "x")
    rules = RoleRuleset()
    from asyncua import ua
    call = ua.NodeId(ua.ObjectIds.CallRequest_Encoding_DefaultBinary)
    read = ua.NodeId(ua.ObjectIds.ReadRequest_Encoding_DefaultBinary)
    assert rules.check_validity(edge, call, None) and rules.check_validity(explorer, read, None)
    assert not rules.check_validity(explorer, call, None)
    assert not OpcUaSecurity.from_env({}).secure


def test_secure_profile_files_are_consistent():
    """Client secrets of the compose override match the generated realm (one source: infra/security.yaml)."""
    from pathlib import Path

    import yaml
    root = Path(__file__).resolve().parents[3]
    realm = json.loads((root / "infra/keycloak/virtual-factory-realm.json").read_text())
    secrets = {c["clientId"]: c.get("secret") for c in realm["clients"]}
    compose = yaml.safe_load((root / "infra/docker-compose.secure.yml").read_text())
    for name, service in compose["services"].items():
        env = service.get("environment") or {}
        if "VF_OIDC_CLIENT_ID" in env:
            assert secrets[env["VF_OIDC_CLIENT_ID"]] == env["VF_OIDC_CLIENT_SECRET"], name
