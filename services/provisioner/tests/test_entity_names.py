"""Entity elements (BoM / HierarchicalStructures nodes) are named after their asset, never "Node"."""

from __future__ import annotations

import pytest

from provisioner.build import build
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
