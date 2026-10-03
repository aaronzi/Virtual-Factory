"""GS1 Digital Link URIs of the products (ADR-0021, ADR-0023): `<domain>/01/<GTIN-14>[/21/<serial>]`, and of
supplier batches (ADR-0028): `<domain>/01/<GTIN-14>/10/<lot>` (GS1 application identifier 10 = batch/lot).

The canonical domain (`https://virtual-factory.example`, reserved TLD, never resolvable) is part of the
identifier (globalAssetId, QR code content). Any GS1 Digital Link resolver can serve a Digital Link: clients
transfer the path to the resolver they are configured with (`rebase`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

CANONICAL_DOMAIN = os.environ.get("VF_DIGITAL_LINK_DOMAIN", "https://virtual-factory.example").rstrip("/")
_PATH = re.compile(r"^/01/(\d{8}|\d{12,14})(?:/10/([^/]{1,20}))?(?:/21/([^/]{1,20}))?/?$")


class InvalidDigitalLink(ValueError):
    pass


def gtin_check_digit(body: str) -> int:
    """GS1 mod-10 check digit of the digits preceding it (weights 3,1,3,... from the right)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def valid_gtin(gtin: str) -> bool:
    return gtin.isdigit() and len(gtin) in (8, 12, 13, 14) and gtin_check_digit(gtin[:-1]) == int(gtin[-1])


@dataclass(frozen=True)
class DigitalLink:
    gtin: str            # GTIN-14
    serial: str | None = None
    lot: str | None = None   # batch / lot number (AI 10)

    @property
    def path(self) -> str:
        return (f"/01/{self.gtin}" + (f"/10/{quote(self.lot, safe='')}" if self.lot else "")
                + (f"/21/{quote(self.serial, safe='')}" if self.serial else ""))

    def uri(self, domain: str = CANONICAL_DOMAIN) -> str:
        """Canonical Digital Link URI (the identifier: globalAssetId, QR content)."""
        return domain.rstrip("/") + self.path

    def rebase(self, resolver_url: str) -> str:
        """The same Digital Link on another resolver (what a scanner app does with its resolver)."""
        return resolver_url.rstrip("/") + self.path

    @property
    def product(self) -> DigitalLink:
        return DigitalLink(self.gtin)


def parse_path(path: str) -> DigitalLink:
    match = _PATH.match(path)
    if not match:
        raise InvalidDigitalLink(f"not a GS1 Digital Link path (01/GTIN[/10/lot][/21/serial]): {path}")
    gtin = match.group(1).zfill(14)
    if not valid_gtin(gtin):
        raise InvalidDigitalLink(f"GTIN {gtin} has a wrong check digit")
    lot, serial = (unquote(g) if g else None for g in match.group(2, 3))
    return DigitalLink(gtin, serial, lot)


def batch_link(gtin: str, lot: str, domain: str = CANONICAL_DOMAIN) -> str:
    """Canonical Digital Link of a batch of a trade item (globalAssetId of a supplier batch AAS)."""
    return DigitalLink(gtin.zfill(14), lot=lot).uri(domain)


def parse(uri: str) -> DigitalLink:
    """Digital Link from a URI with any domain (the domain is not significant for the identification)."""
    return parse_path(urlsplit(uri).path)
