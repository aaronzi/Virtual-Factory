"""Batch records: the facts a supplier states for one delivered lot, derived deterministically from the lot
number and the article's batch profile (simulated production data, reproducible across restarts):
quantity, production and despatch dates, PCF per piece (PACT-like primary data), primary data share, recycled
content (vf_common.lot_values - identical to the MES passport), mean mass and the measured values of the
material certificate EN 10204 3.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from vf_common.digital_link import batch_link
from vf_common.lot_values import lot_uniform, recycled_share

from .articles import Article


@dataclass(frozen=True)
class Measurement:
    characteristic: str
    unit: str
    low: float
    high: float
    actual: float


@dataclass(frozen=True)
class BatchRecord:
    article: Article = field(repr=False)
    lot: str
    quantity: int
    produced: date
    despatched: date
    pcf: float                       # kg CO2e per piece
    primary_share: float             # % of the PCF from primary data
    mean_mass: float                 # kg per piece
    recycled: tuple[float, float] | None  # (pre-consumer %, post-consumer %)
    measurements: dict[str, tuple[Measurement, ...]] = field(repr=False, default_factory=dict)

    @property
    def tag(self) -> str:
        return "BATCH_" + self.lot.replace("-", "_")

    @property
    def asset_id(self) -> str:
        """GS1 Digital Link of the batch (globalAssetId of the batch AAS)."""
        return batch_link(self.article.gtin, self.lot)

    @property
    def aas_id(self) -> str:
        return f"{self.article.id_base}/aas/{self.tag}"

    @property
    def despatch_advice(self) -> str:
        return "DA-" + self.lot

    @property
    def certificate(self) -> str:
        return "MC-" + self.lot


def batch_record(article: Article, lot: str) -> BatchRecord:
    profile = article.profile
    produced = article.produced(lot)
    recycled = _recycled(profile, lot)
    return BatchRecord(article, lot, int(profile["quantity"]), produced,
                       produced + timedelta(days=int(profile.get("leadDays", 2))),
                       batch_pcf(article, lot, recycled), _primary_share(profile, lot),
                       round(_type_mass(article) * (1 + 0.01 * (2 * lot_uniform(lot, "mass") - 1)), 5),
                       recycled, _measurements(profile.get("certificate") or {}, lot))


def batch_pcf(article: Article, lot: str, recycled: tuple[float, float] | None) -> float:
    """declared x (1 + spread x (2u - 1)) - credit x (recycled share - declared recycled share)."""
    profile = article.profile
    declared = article.declared_pcf()
    pcf = declared * (1 + float(profile["pcf"]["spread"]) * (2 * lot_uniform(lot, "energy") - 1))
    if recycled and profile.get("recycled"):
        declared_share = float(profile["recycled"]["pre"]) + float(profile["recycled"]["post"])
        pcf -= float(profile["pcf"]["recycledCredit"]) * (sum(recycled) - declared_share)
    return round(max(pcf, 0.3 * declared), 5)


def _recycled(profile: dict, lot: str) -> tuple[float, float] | None:
    declared = profile.get("recycled")
    if not declared:
        return None
    return (recycled_share(float(declared["pre"]), lot, "pre"),
            recycled_share(float(declared["post"]), lot, "post"))


def _primary_share(profile: dict, lot: str) -> float:
    low, high = profile["primaryDataShare"]
    return float(round(low + (high - low) * lot_uniform(lot, "primary")))


def _type_mass(article: Article) -> float:
    composition = next(s for s in article.spec["submodels"]
                       if s["template"].startswith("ProductMaterialComposition"))
    return float(composition["values"]["TotalMass"])


def _measurements(certificate: dict, lot: str) -> dict[str, tuple[Measurement, ...]]:
    out = {}
    for group in ("analysis", "properties", "dimensions"):
        rows = []
        for name, unit, low, high in certificate.get(group, []):
            u = lot_uniform(lot, f"{group}/{name}")
            actual = float(low) + (float(high) - float(low)) * (0.25 + 0.5 * u)
            rows.append(Measurement(str(name), str(unit), float(low), float(high), actual))
        out[group] = tuple(rows)
    return out
