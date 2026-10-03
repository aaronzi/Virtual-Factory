"""Supplier source of the component footprints (ADR-0028) without servers: batch AAS found via the batch's
Digital Link, fallback to the declared type average, data quality (PACT primary data share) of the part."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from provisioner.build import BuildContext
from sustainability.carbon import PartFootprint
from sustainability.footprint_aas import FootprintWriter
from sustainability.supplier_batches import SupplierBatchFootprints
from sustainability.suppliers import (BomLine, ChainedFootprints, ComponentFootprint, material_footprint,
                                      parse_lots)
from vf_common.resolver import NotResolved

CAP_TYPE, BARREL_TYPE = "urn:asset:CMP_PROTECTIVE_CAP", "urn:asset:CMP_BARREL"
CAP_LOT = "https://virtual-factory.example/01/04099994010016/10/KTW-26-0911"
BOM = [BomLine("Barrel", 1.0, BARREL_TYPE), BomLine("ProtectiveCap", 1.0, CAP_TYPE)]


def _cf(pcf: float, share: float) -> dict:
    entry = [{"modelType": "Property", "idShort": "PcfCO2eq", "value": str(pcf)},
             {"modelType": "Property", "idShort": "PrimaryDataShare", "value": str(share)}]
    return {"id": "urn:sm:cf", "submodelElements": [{"idShort": "ProductCarbonFootprints",
                                                    "value": [{"value": entry}]}]}


class _Resolver:
    """Federated discovery/registry as seen by the source: component types (vf) and supplier batches."""

    def __init__(self):
        self.published = {CAP_LOT: _cf(0.0389, 85)}
        self.down, self.lookups = False, []
        self.types = {CAP_TYPE: [{"name": "gtin", "value": "04099994010016"}], BARREL_TYPE: []}

    def resolve_asset(self, asset_id):
        self.lookups.append(asset_id)
        if self.down:
            raise httpx.ConnectError("supplier environment down")
        if asset_id in self.types:
            return SimpleNamespace(descriptor={"specificAssetIds": self.types[asset_id]}, aas_id=asset_id)
        if asset_id in self.published:
            return SimpleNamespace(aas_id=asset_id, environment="supplier", descriptor={})
        raise NotResolved(asset_id)

    def submodel_of(self, aas_id, semantic_id=None):
        return SimpleNamespace(id=aas_id)

    def repository(self, endpoint):
        return SimpleNamespace(get_submodel=lambda sm_id: self.published[sm_id])


class _Declared:
    def footprint(self, line, batch):
        return ComponentFootprint({"Barrel": 1.72, "ProtectiveCap": 0.04}[line.node], "component-type-aas")


def test_batch_footprint_from_the_supplier_batch_aas_is_primary_data():
    source = SupplierBatchFootprints(_Resolver())
    found = source.footprint(BOM[1], "KTW-26-0911")
    assert (found.pcf_kg, found.source, found.data_quality, found.primary_share) == (0.0389, "supplier-batch",
                                                                                    "primary", 85.0)
    assert found.asset_id == CAP_LOT and found.batch == "KTW-26-0911"
    assert source.footprint(BOM[0], "L2609-0419") is None  # in-house component: no GTIN, no supplier batch


def test_unknown_batches_fall_back_and_are_asked_again_later():
    resolver, now = _Resolver(), [0.0]
    source = SupplierBatchFootprints(resolver, miss_ttl_s=30, clock=lambda: now[0])
    chain = ChainedFootprints(source, _Declared())
    lots = parse_lots("Barrel=L2609-0419;ProtectiveCap=KTW-26-0912")
    total, details = material_footprint(BOM, lots, chain)
    assert total == pytest.approx(1.72 + 0.04)
    assert [d["dataQuality"] for d in details] == ["secondary", "secondary"]
    resolver.published[CAP_LOT.replace("0911", "0912")] = _cf(0.041, 80)  # published by the supplier now
    material_footprint(BOM, lots, chain)
    assert resolver.lookups.count(CAP_LOT.replace("0911", "0912")) == 1  # miss cached for 30 s
    now[0] = 31.0
    total, details = material_footprint(BOM, lots, chain)
    assert total == pytest.approx(1.72 + 0.041) and details[1]["source"] == "supplier-batch"


def test_unreachable_supplier_environment_uses_the_declared_average_without_caching():
    resolver = _Resolver()
    source = SupplierBatchFootprints(resolver)
    source.footprint(BOM[1], "KTW-26-0911")  # GTIN of the type cached
    resolver.down = True
    assert ChainedFootprints(SupplierBatchFootprints(resolver), _Declared()).footprint(
        BOM[1], "KTW-26-0911").source == "component-type-aas"
    fresh = SupplierBatchFootprints(resolver)
    assert fresh.footprint(BOM[1], "KTW-26-0911") is None
    resolver.down = False
    assert fresh.footprint(BOM[1], "KTW-26-0911").data_quality == "primary"


def test_primary_data_share_of_the_part_and_its_carbon_footprint_submodel():
    components = ({"node": "Barrel", "count": 1.0, "pcf": 1.72, "dataQuality": "secondary",
                   "primaryShare": 0},
                  {"node": "ProtectiveCap", "count": 1.0, "pcf": 0.04, "dataQuality": "primary",
                   "primaryShare": 85.0})
    fp = PartFootprint(1.76, 0.02, 0.0, 0.5, components=components)  # A3 = 0.01 kg (measured: primary)
    assert fp.supplier_specific_share == pytest.approx(100 * 0.04 / 1.76)
    assert fp.material_primary_share == pytest.approx(100 * 0.034 / 1.76)
    assert fp.primary_share == pytest.approx(100 * (0.034 + 0.01) / 1.77)
    sm, _ = FootprintWriter(aas=None, ctx=BuildContext()).build("PC3280-2026-000778", fp,
                                                                 "2026-10-03T10:00:19.000Z")
    entries = sm["submodelElements"][0]["value"]
    values = [{e["idShort"]: e.get("value") for e in entry["value"]} for entry in entries]
    assert float(values[0]["PrimaryDataShare"]) == round(fp.primary_share, 1)
    assert float(values[1]["PrimaryDataShare"]) == round(fp.material_primary_share, 1)
    assert float(values[1]["SupplierSpecificDataShare"]) == round(fp.supplier_specific_share, 1)
