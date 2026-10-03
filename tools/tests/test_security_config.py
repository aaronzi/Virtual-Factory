"""Generated configuration of the secure profile (tools/gen_security_config.py, ADR-0027): files up to date,
ABAC rules (ownership, passport sections), Keycloak realm and Mosquitto ACLs."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
_spec = importlib.util.spec_from_file_location("gen_security_config", TOOLS / "gen_security_config.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

import security_abac  # noqa: E402
import security_model  # noqa: E402

MODEL = security_model.load()
FILES = gen.render(MODEL)


def _file(name: str) -> str:
    return next(text for path, text in FILES.items() if path.name == name)


def _rules(section: str) -> list[dict]:
    return security_abac.access_rules(MODEL, section)["AllAccessPermissionRules"]["rules"]


def _roles(rule: dict) -> set[str]:
    text = json.dumps(rule["FORMULA"])
    return {r for r in [*MODEL["roles"], *[f"svc-{s}" for s in MODEL["services"]]] if f'"{r}"' in text}


def test_generated_files_are_up_to_date():
    stale = [str(p.relative_to(gen.ROOT)) for p, text in FILES.items()
             if not p.exists() or p.read_text(encoding="utf-8") != text]
    assert not stale, f"run uv run tools/gen_security_config.py: {stale}"


def test_group_references_expand_recursively():
    assert security_model.expand(MODEL, "@public") == ["ANONYMOUS", "public"]
    recycler = security_model.expand(MODEL, ["@passport.public", "@passport.recycler"])
    assert "ProductMaterialComposition" in recycler and "Nameplate" in recycler


def test_mes_writes_workpieces_but_not_their_carbon_footprint():
    writes = [r for r in _rules("aas_env") if "svc-mes" in _roles(r) and "UPDATE" in r["ACL"]["RIGHTS"]
              and r["USEOBJECTS"] == ["submodels"]]
    workpiece = next(r for r in writes if "/sm/WP_" in json.dumps(r["FORMULA"]))
    not_pcf = {"$ne": [{"$field": "$sm#idShort"}, {"$strVal": "CarbonFootprint"}]}
    assert not_pcf in workpiece["FORMULA"]["$and"]
    sustainability = [r for r in _rules("aas_env") if _roles(r) == {"svc-sustainability"}
                      and "CREATE" in r["ACL"]["RIGHTS"] and r["USEOBJECTS"] == ["submodels"]]
    assert "CarbonFootprint" in json.dumps(sustainability)


def test_anonymous_rules_only_read():
    anonymous = [r for section in ("aas_env", "dpp_api", "supplier_env") for r in _rules(section)
                 if r["ACL"]["USEATTRIBUTES"] == "anonymous"]
    assert anonymous and all(r["ACL"]["RIGHTS"] == ["READ"] for r in anonymous)


def test_dpp_sections_per_audience():
    rules = _rules("dpp_api")
    public = next(r for r in rules if r["ACL"]["USEATTRIBUTES"] == "anonymous")
    pattern = public["FILTER"]["CONDITION"]["$regex"][1]["$strVal"]
    assert "Nameplate" in pattern and "ProductMaterialComposition" not in pattern
    recycler = next(r for r in rules if _roles(r) == {"recycler"})
    assert "ProductMaterialComposition" in recycler["FILTER"]["CONDITION"]["$regex"][1]["$strVal"]
    auditor = next(r for r in rules if "auditor" in _roles(r))
    assert "FILTER" not in auditor, "auditors read the full passport"


def test_realm_has_roles_users_and_service_clients():
    realm = json.loads(_file("virtual-factory-realm.json"))
    roles = {r["name"] for r in realm["roles"]["realm"]}
    assert {"operator", "quality", "maintenance", "planner", "auditor", "authority", "recycler", "public",
            "svc-mes", "svc-resolver"} <= roles
    clients = {c["clientId"]: c for c in realm["clients"]}
    assert clients["vf-mes"]["serviceAccountsEnabled"] and not clients["vf-mes"]["publicClient"]
    assert clients["vf-godot"]["publicClient"] and clients["vf-godot"]["directAccessGrantsEnabled"]
    assert clients["vf-aas-ui"]["attributes"]["pkce.code.challenge.method"] == "S256"
    resolver = next(u for u in realm["users"] if u.get("serviceAccountClientId") == "vf-resolver")
    assert resolver["realmRoles"] == ["svc-resolver", "public"]
    assert all(m["config"].get("included.custom.audience") == "virtual-factory-api"
               for c in realm["clients"] for m in c["protocolMappers"] if m["name"] == "vf-api-audience")


def test_mqtt_acl_only_gateway_publishes_commands():
    acl = _file("acl")
    blocks = {b.splitlines()[0][5:]: b.splitlines()[1:] for b in acl.split("\n\n") if b.startswith("user ")}
    cmd = "vf/plant01/final-assembly/line01/+/cmd/+"
    writers = {u for u, lines in blocks.items() if f"topic write {cmd}" in lines}
    assert writers == {"ops-gateway"}
    assert f"topic read {cmd}" in blocks["godot"]
    assert all(not line.startswith("topic write") for line in blocks["historian"] + blocks["explorer"])
    assert "topic deny vf/plant01/final-assembly/line01/maintenance/#" in blocks["godot"]
    assert set(blocks) == {line.split(":")[0] for line in _file("passwords").splitlines()}
