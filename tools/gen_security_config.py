#!/usr/bin/env python3
"""Generates the configuration of the optional secure profile from infra/security.yaml (ADR-0027):

    infra/keycloak/virtual-factory-realm.json          Keycloak realm import
    infra/basyx/security/trustlist.json                OIDC trust list of the BaSyx services
    infra/basyx/security/{aas-env,dpp-api,supplier-env}.rules.json   ABAC access rules
    infra/mosquitto/secure/acl, infra/mosquitto/secure/passwords      broker ACL and accounts

Usage: uv run tools/gen_security_config.py [--check]   (--check: fail if a file is out of date)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import security_abac
import security_model
import security_mqtt

ROOT = security_model.ROOT
UNS = ROOT / "godot" / "config" / "uns.json"


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render(model: dict | None = None, uns: dict | None = None) -> dict[Path, str]:
    model = model or security_model.load()
    uns = uns or json.loads(UNS.read_text(encoding="utf-8"))
    basyx = ROOT / "infra" / "basyx" / "security"
    mqtt = ROOT / "infra" / "mosquitto" / "secure"
    return {
        ROOT / "infra" / "keycloak" / "virtual-factory-realm.json": _json(security_model.realm(model)),
        basyx / "trustlist.json": _json(security_abac.trustlist(model)),
        basyx / "aas-env.rules.json": _json(security_abac.access_rules(model, "aas_env")),
        basyx / "dpp-api.rules.json": _json(security_abac.access_rules(model, "dpp_api")),
        basyx / "supplier-env.rules.json": _json(security_abac.access_rules(model, "supplier_env")),
        mqtt / "acl": security_mqtt.acl(model, uns),
        mqtt / "passwords": security_mqtt.passwords(model),
    }


def main() -> int:
    files = render()
    if "--check" in sys.argv:
        stale = [p for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date; run tools/gen_security_config.py")
        return 1 if stale else 0
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
