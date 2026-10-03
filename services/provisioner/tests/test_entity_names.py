"""Entity elements (BoM / HierarchicalStructures nodes) are named after their asset, never "Node"."""

from __future__ import annotations

import pytest

from provisioner.build import DATA_SETS, build, load_assets
from vf_common import ids
from vf_common.aas.entities import _entities


@pytest.fixture(scope="module")
def env():
    return build(blueprints=True).environment


def _texts(element: dict, key: str) -> dict[str, str]:
    return {t["language"]: t["text"] for t in element.get(key) or []}


def test_no_entity_keeps_the_template_name(env):
    for sm in env["submodels"]:
        for entity in _entities(sm["submodelElements"]):
            names = _texts(entity, "displayName")
            assert names.get("en") not in (None, "Node", "Entry Node"), (sm["id"], entity["idShort"])


def test_bom_nodes_carry_the_component_names(env):
    shells = {s["assetInformation"]["globalAssetId"]: s for s in env["assetAdministrationShells"]}
    bom_id = ids.submodel_id("PC3280_TYPE", "HierarchicalStructures", "1")
    bom = next(sm for sm in env["submodels"] if sm["id"] == bom_id)
    nodes = [e for e in _entities(bom["submodelElements"]) if e.get("globalAssetId") in shells]
    assert len(nodes) >= 10  # entry node + 9 component types
    for node in nodes:
        assert _texts(node, "displayName") == _texts(shells[node["globalAssetId"]], "displayName")
        assert set(_texts(node, "displayName")) == {"en", "de"}


def test_batch_nodes_of_the_as_built_bom(env):
    """Workpiece blueprint (aas-model.md §6b, ADR-0028): purchased batches have their own AAS in the supplier
    environment - SelfManagedEntity with the batch's Digital Link (GTIN of the supplier's product type + lot);
    in-house lots have none - CoManagedEntity without asset ids (AASd-014). Each is named after its batch."""
    bom_id = ids.submodel_id("WP_PC3280_2026_000123", "HierarchicalStructures", "1")
    bom = next(sm for sm in env["submodels"] if sm["id"] == bom_id)
    entry = next(e for e in bom["submodelElements"] if e["idShort"] == "EntryNode")
    nodes = [e for e in entry["statements"] if e["modelType"] == "Entity"]
    supplier_types = {s["globalAssetId"] for s in load_assets(DATA_SETS["supplier"]) if s["kind"] == "Type"}
    for node in nodes:
        lot = next(s["value"] for s in node["statements"] if s["idShort"] == "BatchId")
        assert lot in _texts(node, "displayName")["en"]
        if node["entityType"] == "SelfManagedEntity":
            product, _, batch = node["globalAssetId"].partition("/10/")
            assert product in supplier_types and batch == lot
        else:
            assert node["entityType"] == "CoManagedEntity"
            assert not node.get("globalAssetId") and not node.get("specificAssetIds")
    assert sum(n["entityType"] == "SelfManagedEntity" for n in nodes) == 5
