"""Uploads (replaces) all AAS, submodels and concept descriptions on a running AAS repository server."""

from __future__ import annotations

import base64

import httpx


def _b64(identifier: str) -> str:
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


def upload(env: dict, builder, url: str) -> None:
    with httpx.Client(base_url=url, timeout=30) as http:
        for cd in env["conceptDescriptions"]:
            _put_or_post(http, "/concept-descriptions", cd)
        for sm in env["submodels"]:
            _put_or_post(http, "/submodels", sm)
        for shell in env["assetAdministrationShells"]:
            _put_or_post(http, "/shells", shell)
    print(f"uploaded {len(env['assetAdministrationShells'])} AAS to {url}")


def _put_or_post(http: httpx.Client, collection: str, obj: dict) -> None:
    response = http.put(f"{collection}/{_b64(obj['id'])}", json=obj)
    if response.status_code == 404:
        response = http.post(collection, json=obj)
    if response.status_code >= 300:
        raise RuntimeError(f"{collection} {obj['id']}: HTTP {response.status_code} {response.text[:300]}")
