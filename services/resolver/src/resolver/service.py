"""Resolution of a GS1 Digital Link: the canonical URI is the globalAssetId of the product (type) or item AAS
(ADR-0021). Discovery + registry give the AAS endpoints, the BaSyx DPP API the passport (by product id)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from vf_common.basyx import BasyxError
from vf_common.digital_link import DigitalLink
from vf_common.resolver import AasResolver, NotResolved, ShellEndpoint

from .links import Link, Urls, build_links, descriptor_url

log = logging.getLogger("resolver")


@dataclass(frozen=True)
class Resolution:
    dl: DigitalLink
    anchor: str                 # canonical Digital Link URI
    shell: ShellEndpoint | None
    dpp: dict | None
    links: list[Link]

    def link(self, link_type: str) -> Link | None:
        return next((k for k in self.links if k.link_type == link_type), None)


class DigitalLinkResolver:
    def __init__(self, aas: AasResolver, dpp_url: str, urls: Urls, http: httpx.Client | None = None):
        self.aas, self.dpp_url, self.urls = aas, dpp_url.rstrip("/"), urls
        self.http = http or httpx.Client(timeout=10.0)

    def resolve(self, dl: DigitalLink) -> Resolution | None:
        """None if neither an AAS nor a passport exists for the Digital Link."""
        anchor = dl.uri()
        shell = self._shell(anchor)
        dpp = self.passport(anchor)
        if shell is None and dpp is None:
            return None
        descriptor = None
        if shell is not None:
            environment = next(e for e in self.aas.config.environments if e.name == shell.environment)
            descriptor = descriptor_url(self.aas.config.public(environment.aas_registry), shell.aas_id)
        links = build_links(dl, self.urls, dpp, shell.href if shell else None, descriptor)
        return Resolution(dl, anchor, shell, dpp, links)

    def passport(self, product_id: str) -> dict | None:
        """Passport (compressed representation) from the DPP API by product id, None if there is none."""
        try:
            response = self.http.get(f"{self.dpp_url}/v1/dppsByProductId/{quote(product_id, safe='')}")
        except httpx.HTTPError as exc:
            log.warning("DPP API unreachable: %s", exc)
            return None
        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            log.warning("DPP API: HTTP %d for %s", response.status_code, product_id)
        return None

    def _shell(self, anchor: str) -> ShellEndpoint | None:
        try:
            return self.aas.resolve_asset(anchor)
        except NotResolved:
            return None
        except (httpx.HTTPError, BasyxError) as exc:
            log.warning("discovery / registry unreachable: %s", exc)
            return None
