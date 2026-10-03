"""Uploads (replaces) all AAS, submodels and concept descriptions on a running AAS repository server."""

from __future__ import annotations

from vf_common.basyx import BasyxClient


def upload(env: dict, builder, url: str) -> None:
    client = BasyxClient(url, timeout=30)
    try:
        for cd in env["conceptDescriptions"]:
            client.put_concept_description(cd)
        for sm in env["submodels"]:
            client.put_submodel(sm)
        for shell in env["assetAdministrationShells"]:
            client.put_shell(shell)
    finally:
        client.close()
    print(f"uploaded {len(env['assetAdministrationShells'])} AAS to {url}")
