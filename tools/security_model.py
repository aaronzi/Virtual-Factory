"""Security model of the secure profile (infra/security.yaml): loading, `@group` expansion and the Keycloak
realm export built from it (used by tools/gen_security_config.py, ADR-0027)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "infra" / "security.yaml"
ANONYMOUS = "ANONYMOUS"


def load(path: Path = MODEL) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def expand(model: dict, value: Any) -> list[str]:
    """Resolves "@group" / "@passport.public" references (recursively) into a flat, ordered list."""
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and item.startswith("@"):
            node: Any = model["groups"] if "." not in item else model
            for part in (item[1:].split(".") if "." in item else [item[1:]]):
                node = node[part]
            resolved = expand(model, node)
        else:
            resolved = [item]
        out += [r for r in resolved if r not in out]
    return out


def service_role(name: str) -> str:
    return f"svc-{name}"


def service_secret(name: str) -> str:
    return f"vf-{name}-local-secret"


def client_secret(client_id: str) -> str:
    return f"{client_id}-local-secret"


# -- Keycloak realm ------------------------------------------------------------------------------------------

def _audience_mapper(audience: str) -> dict:
    return {"name": "vf-api-audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
            "config": {"included.custom.audience": audience, "access.token.claim": "true",
                       "id.token.claim": "false", "introspection.token.claim": "true"}}


def _roles_mapper() -> dict:
    """Realm roles also as top-level claim "roles" in ID token and userinfo (Grafana role mapping)."""
    return {"name": "realm-roles-claim", "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-realm-role-mapper",
            "config": {"claim.name": "roles", "multivalued": "true", "jsonType.label": "String",
                       "access.token.claim": "true", "id.token.claim": "true", "userinfo.token.claim": "true",
                       "introspection.token.claim": "true"}}


def _client(client_id: str, description: str, audience: str, **flags: Any) -> dict:
    base = {"clientId": client_id, "name": client_id, "description": description, "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False, "implicitFlowEnabled": False,
            "frontchannelLogout": True, "fullScopeAllowed": True,
            "protocolMappers": [_audience_mapper(audience), _roles_mapper()], "attributes": {}}
    base.update(flags)
    return base


def _service_clients(model: dict) -> list[dict]:
    return [_client(f"vf-{name}", description, model["audience"], secret=service_secret(name),
                    serviceAccountsEnabled=True, clientAuthenticatorType="client-secret")
            for name, description in model["services"].items()]


def _interactive_clients(model: dict) -> list[dict]:
    out = []
    for client_id, spec in model["clients"].items():
        flags: dict[str, Any] = {"publicClient": spec["type"] == "public"}
        if spec.get("redirect"):
            flags.update(standardFlowEnabled=True, redirectUris=[spec["redirect"]],
                         webOrigins=[spec.get("origin", "+")],
                         attributes={"pkce.code.challenge.method": "S256",
                                     "post.logout.redirect.uris": spec.get("origin", "") + "/*"})
        if spec.get("password_grant"):
            flags["directAccessGrantsEnabled"] = True
        if spec.get("device_grant"):
            flags["attributes"] = {**flags.get("attributes", {}),
                                   "oauth2.device.authorization.grant.enabled": "true"}
        if spec["type"] == "confidential":
            flags.update(secret=client_secret(client_id), clientAuthenticatorType="client-secret")
        out.append(_client(client_id, spec["description"], model["audience"], **flags))
    return out


def _users(model: dict) -> list[dict]:
    users = [{"username": name, "enabled": True, "emailVerified": True,
              "firstName": name.rstrip("0123456789").capitalize(),
              "lastName": "Training", "requiredActions": [], "email": f"{name}@virtual-factory.example",
              "credentials": [{"type": "password", "value": model["user_password"], "temporary": False}],
              "realmRoles": roles}
             for name, roles in model["users"].items()]
    for name in model["services"]:
        roles = [service_role(name), *model.get("service_extra_roles", {}).get(name, [])]
        users.append({"username": f"service-account-vf-{name}", "enabled": True,
                      "serviceAccountClientId": f"vf-{name}", "realmRoles": roles})
    return users


def realm(model: dict) -> dict:
    roles = [{"name": name, "description": text} for name, text in model["roles"].items()]
    roles += [{"name": service_role(name), "description": f"Service account: {text}"}
              for name, text in model["services"].items()]
    return {"realm": model["realm"], "displayName": "Virtual Factory (training, local defaults)",
            "enabled": True, "sslRequired": "none", "registrationAllowed": False,
            "loginWithEmailAllowed": False,
            "accessTokenLifespan": 300, "ssoSessionIdleTimeout": 3600,
            "oauth2DeviceCodeLifespan": 600, "oauth2DevicePollingInterval": 5,
            "roles": {"realm": roles}, "users": _users(model),
            "clients": _service_clients(model) + _interactive_clients(model)}
