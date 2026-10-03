"""BaSyx Go ABAC access rules (IDTA Part 4 access rule model, BaSyx Go v1.1 dialect) from the grants of
infra/security.yaml (aas_env, dpp_api, supplier_env) and the OIDC trust list (ADR-0027).

A grant {roles, rights, objects, [aas_prefix | sm_prefix | id_short | not_id_short | sections]} becomes one
rule per subject kind: anonymous requests (GLOBAL=ANONYMOUS) and token holders (realm role in
/realm_access/roles). Field conditions on `$aas#id`, `$sm#id`, `$sm#idShort` are left to BaSyx as residual
query filters (evaluated per resource, also for created/updated content)."""

from __future__ import annotations

from typing import Any

from security_model import ANONYMOUS, expand

ROLES_CLAIM = "/realm_access/roles"
ID_BASE = "https://virtual-factory.example/ids"


def _str(value: str) -> dict:
    return {"$strVal": value}


def has_role(role: str) -> dict:
    return {"$contains": [{"$attribute": {"CLAIMPATH": ROLES_CLAIM}}, _str(role)]}


def _any(terms: list[dict]) -> dict:
    return terms[0] if len(terms) == 1 else {"$or": terms}


def _all(terms: list[dict]) -> dict:
    if not terms:
        return {"$boolean": True}
    return terms[0] if len(terms) == 1 else {"$and": terms}


def field_conditions(model: dict, grant: dict) -> list[dict]:
    terms = []
    if grant.get("aas_prefix"):
        terms.append({"$starts-with": [{"$field": "$aas#id"}, _str(f"{ID_BASE}/aas/{grant['aas_prefix']}")]})
    if grant.get("sm_prefix"):
        terms.append({"$starts-with": [{"$field": "$sm#id"}, _str(f"{ID_BASE}/sm/{grant['sm_prefix']}")]})
    if grant.get("id_short"):
        terms.append(_any([{"$eq": [{"$field": "$sm#idShort"}, _str(s)]}
                           for s in expand(model, grant["id_short"])]))
    for excluded in expand(model, grant.get("not_id_short", [])):
        terms.append({"$ne": [{"$field": "$sm#idShort"}, _str(excluded)]})
    return terms


def section_filter(model: dict, grant: dict) -> dict:
    """Fragment filter that hides the AAS's references to submodels outside the listed sections (idShort as
    path segment of the submodel id, vf_common.ids). The DPP API composes a passport from exactly these
    references, so the passport shows only the permitted sections."""
    names = "|".join(expand(model, grant["sections"]))
    return {"FRAGMENT": "$aas#submodels[]", "MATCH": True,
            "CONDITION": {"$regex": [{"$field": "$aas#submodels[].keys[].value"},
                                     _str(f"/sm/[^/]+/({names})/[^/]+$")]}}


def rules_for(model: dict, grant: dict) -> list[dict]:
    roles = expand(model, grant["roles"])
    conditions = field_conditions(model, grant)
    objects = [grant["objects"]] if isinstance(grant["objects"], str) else grant["objects"]
    extra = {"FILTER": section_filter(model, grant)} if grant.get("sections") else {}
    out = []
    if ANONYMOUS in roles:
        out.append({"ACL": {"USEATTRIBUTES": "anonymous", "RIGHTS": grant["rights"], "ACCESS": "ALLOW"},
                    "USEOBJECTS": objects, "FORMULA": _all(conditions), **extra})
    named = [r for r in roles if r != ANONYMOUS]
    if named:
        out.append({"ACL": {"USEATTRIBUTES": "realm_roles", "RIGHTS": grant["rights"], "ACCESS": "ALLOW"},
                    "USEOBJECTS": objects, "FORMULA": _all([_any([has_role(r) for r in named]), *conditions]),
                    **extra})
    return out


def access_rules(model: dict, section: str) -> dict:
    grants = model[section]
    used = []
    for grant in grants:
        for name in ([grant["objects"]] if isinstance(grant["objects"], str) else grant["objects"]):
            if name not in used:
                used.append(name)
    return {"AllAccessPermissionRules": {
        "DEFATTRIBUTES": [{"name": "anonymous", "attributes": [{"GLOBAL": "ANONYMOUS"}]},
                          {"name": "realm_roles", "attributes": [{"CLAIMPATH": ROLES_CLAIM}]}],
        "DEFOBJECTS": [{"name": name, "objects": [{"ROUTE": r} for r in model["objects"][name]]}
                       for name in used],
        "rules": [rule for grant in grants for rule in rules_for(model, grant)]}}


def trustlist(model: dict) -> list[dict[str, Any]]:
    return [{"issuer": model["issuer"], "audience": model["audience"],
             "discoveryUrl": model["discovery_url"]}]
