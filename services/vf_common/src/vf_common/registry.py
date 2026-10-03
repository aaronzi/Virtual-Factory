"""Clients for the AAS infrastructure services that locate an AAS (AAS Part 2 HTTP API, V3.x): Discovery
(`/lookup/shells`, asset id -> AAS ids) and the AAS / Submodel Registries (`/shell-descriptors`,
`/submodel-descriptors`, AAS id -> descriptor with endpoints). See ADR-0023.

`RegistryConfig` lists the infrastructure endpoints of one or more AAS environments (federation: the own
BaSyx environment, later e.g. a supplier's), plus a prefix map that rewrites the public endpoint URLs written
into descriptors (`GENERAL_EXTERNALURL`) to addresses reachable from where the client runs (compose network).
Authentication is injectable (`httpx.Auth`), so a token provider can be added without touching the callers.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from .basyx import BasyxError, b64


@dataclass(frozen=True)
class Environment:
    """Infrastructure endpoints of one AAS environment (BaSyx Go serves all three at the same base URL)."""
    name: str
    discovery: str
    aas_registry: str
    submodel_registry: str

    @classmethod
    def at(cls, name: str, base_url: str) -> Environment:
        base = base_url.rstrip("/")
        return cls(name, base, base, base)


@dataclass(frozen=True)
class RegistryConfig:
    environments: tuple[Environment, ...]
    endpoint_map: Mapping[str, str] = field(default_factory=dict)  # public URL prefix -> reachable prefix
    cache_ttl_s: float = 300.0
    timeout_s: float = 10.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RegistryConfig:
        """VF_AAS_REGISTRIES: `name=base,name2=base2` (BaSyx environments) or a JSON list of
        {name, discovery, aas_registry, submodel_registry}; default `vf=$VF_AAS_URL`.
        VF_AAS_ENDPOINT_MAP: `public=reachable,...`; default maps VF_AAS_PUBLIC_URL to VF_AAS_URL."""
        env = os.environ if env is None else env
        aas_url = env.get("VF_AAS_URL", "http://localhost:8091").rstrip("/")
        environments = parse_environments(env.get("VF_AAS_REGISTRIES", "") or f"vf={aas_url}")
        public = env.get("VF_AAS_PUBLIC_URL", aas_url).rstrip("/")
        mapping = parse_pairs(env.get("VF_AAS_ENDPOINT_MAP", "")) or ({public: aas_url} if public != aas_url
                                                                      else {})
        return cls(environments, mapping, float(env.get("VF_AAS_RESOLVER_TTL", "300")))

    def reachable(self, url: str) -> str:
        """Rewrites a descriptor endpoint (public URL) to the address reachable from this process."""
        for public, local in self.endpoint_map.items():
            if url.startswith(public.rstrip("/")):
                return local.rstrip("/") + url[len(public.rstrip("/")):]
        return url

    def public(self, url: str) -> str:
        """Inverse of `reachable`: the public form of an internal URL (for links handed to browsers)."""
        for public, local in self.endpoint_map.items():
            if url.startswith(local.rstrip("/")):
                return public.rstrip("/") + url[len(local.rstrip("/")):]
        return url


def parse_environments(text: str) -> tuple[Environment, ...]:
    text = text.strip()
    if text.startswith("["):
        return tuple(Environment(e["name"], e["discovery"].rstrip("/"), e["aas_registry"].rstrip("/"),
                                 e["submodel_registry"].rstrip("/")) for e in json.loads(text))
    return tuple(Environment.at(name, url) for name, url in parse_pairs(text).items())


def parse_pairs(text: str) -> dict[str, str]:
    pairs = {}
    for item in filter(None, (p.strip() for p in text.split(","))):
        key, _, value = item.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def asset_link(name: str, value: str) -> str:
    """Query value of `assetIds` (base64url of a SpecificAssetId JSON, no padding)."""
    return b64(json.dumps({"name": name, "value": value}, separators=(",", ":")))


class InfrastructureClient:
    """Discovery + registry calls against one environment."""

    def __init__(self, environment: Environment, client: httpx.Client):
        self.environment, self.http = environment, client

    def lookup_shells(self, asset_ids: Mapping[str, str]) -> list[str]:
        """AAS ids whose asset matches ALL given asset ids ({"globalAssetId": iri, "serialNumber": ...})."""
        params = [("assetIds", asset_link(k, v)) for k, v in asset_ids.items()]
        body = self._get(f"{self.environment.discovery}/lookup/shells", params)
        return list(body.get("result", [])) if body else []

    def asset_links(self, aas_id: str) -> list[dict]:
        body = self._get(f"{self.environment.discovery}/lookup/shells/{b64(aas_id)}")
        return body if isinstance(body, list) else []

    def shell_descriptor(self, aas_id: str) -> dict | None:
        return self._get(f"{self.environment.aas_registry}/shell-descriptors/{b64(aas_id)}")

    def submodel_descriptor(self, sm_id: str) -> dict | None:
        return self._get(f"{self.environment.submodel_registry}/submodel-descriptors/{b64(sm_id)}")

    def submodel_descriptors(self, limit: int = 500) -> list[dict]:
        url, items, cursor = f"{self.environment.submodel_registry}/submodel-descriptors", [], None
        while True:
            body = self._get(url, {"limit": limit, **({"cursor": cursor} if cursor else {})}) or {}
            items += body.get("result", [])
            cursor = (body.get("paging_metadata") or {}).get("cursor")
            if not cursor:
                return items

    def _get(self, url: str, params=None):
        response = self.http.get(url, params=params)
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise BasyxError("GET", url, response)
        return response.json()


def endpoint_href(descriptor: dict, interface_prefix: str) -> str | None:
    """First http(s) endpoint of a descriptor whose interface starts with e.g. "AAS-" or "SUBMODEL-"."""
    for endpoint in descriptor.get("endpoints") or []:
        info = endpoint.get("protocolInformation") or {}
        if str(endpoint.get("interface", "")).startswith(interface_prefix) and info.get("href"):
            return info["href"]
    return None


def repository_base(href: str) -> str:
    """Repository base URL of a shell / submodel endpoint (`<base>/shells/<id>`, `<base>/submodels/<id>`)."""
    for marker in ("/shells/", "/submodels/"):
        if marker in href:
            return href.rsplit(marker, 1)[0]
    return href.rstrip("/")


def decode_id(encoded: str) -> str:
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()

