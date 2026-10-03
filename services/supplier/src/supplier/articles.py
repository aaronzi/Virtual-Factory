"""Supplier articles known to the portal: product type AAS of the suppliers (aas/data/supplier/assets), the
companies that publish them and their batch profiles (aas/data/supplier/batch_profiles.yaml).

An article is found by the customer's or the supplier's article number; a lot belongs to it if it matches the
supplier's lot format (regex of the profile). Lots of other formats are not this supplier's (e.g. in-house
lots of VF Pneumatics, L<YYWW>-<n>)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from provisioner.build import DATA_SETS, load_assets

SUPPLIER_DATA = DATA_SETS["supplier"]


@dataclass(frozen=True)
class Company:
    tag: str
    name: str            # official name (CompanyData.CompanyIdentification.CompanyName)
    domain_id: str       # document domain id (AAS idShort of the company)
    gln: str

    @property
    def short_name(self) -> str:
        return self.name.removesuffix(" GmbH")


@dataclass(frozen=True)
class Article:
    tag: str             # tag of the product type AAS
    spec: dict = field(repr=False)
    profile: dict = field(repr=False)
    company: Company = field(repr=False)

    @property
    def id_base(self) -> str:
        return self.spec["idBase"]

    @property
    def gtin(self) -> str:
        return str(self.spec["specificAssetIds"]["gtin"])

    @property
    def part_id(self) -> str:
        return str(self.spec["specificAssetIds"]["manufacturerPartId"])

    @property
    def customer_part_id(self) -> str:
        return str(self.profile["customerPartId"])

    @property
    def name(self) -> dict[str, str]:
        return {lang: text.removesuffix(" (product type)").removesuffix(" (Produkttyp)")
                for lang, text in self.spec["displayName"].items()}

    def owns(self, lot: str) -> bool:
        return re.match(self.profile["lot"]["pattern"], lot) is not None

    def produced(self, lot: str) -> date:
        """Production date of a lot: cast date in the lot number, or derived from its sequence number."""
        match = re.match(self.profile["lot"]["pattern"], lot)
        if match is None:
            raise ValueError(f"{lot} is not a lot of {self.part_id}")
        groups = match.groupdict()
        if groups.get("date"):
            text = groups["date"]
            return date(2000 + int(text[:2]), int(text[2:4]), int(text[4:]))
        spec = self.profile["lot"]
        days = (int(groups["seq"]) - int(spec["firstSeq"])) * int(spec["daysPerLot"])
        return date.fromisoformat(spec["firstDate"]) + timedelta(days=days)

    def declared_pcf(self) -> float:
        """Declared average PCF of the type (first entry of its CarbonFootprint)."""
        cf = next(s for s in self.spec["submodels"] if s["template"].startswith("CarbonFootprint"))
        return float(cf["values"]["ProductCarbonFootprints"][0]["PcfCO2eq"])


class Catalogue:
    def __init__(self, data_dir: Path = SUPPLIER_DATA):
        specs = load_assets(data_dir)
        profiles = yaml.safe_load((data_dir / "batch_profiles.yaml").read_text())
        companies = {s["idBase"]: _company(s) for s in specs if _is_company(s)}
        self.specs = {s["tag"]: s for s in specs}
        self.articles = {tag: Article(tag, self.specs[tag], profile, companies[self.specs[tag]["idBase"]])
                         for tag, profile in profiles.items()}

    def find(self, article: str) -> Article | None:
        """Article by customer part id, manufacturer part id or product type tag."""
        return next((a for a in self.articles.values()
                     if article in (a.customer_part_id, a.part_id, a.tag)), None)


def _is_company(spec: dict) -> bool:
    return any(s["template"].startswith("CompanyData") for s in spec["submodels"])


def _company(spec: dict) -> Company:
    data = next(s["values"] for s in spec["submodels"] if s["template"].startswith("CompanyData"))
    return Company(spec["tag"], data["CompanyIdentification"]["CompanyName"], spec["idShort"],
                   str((spec.get("specificAssetIds") or {}).get("gln", "")))
