"""Smoke test: basyx-python-sdk serialisation round-trips through BaSyx Go (risk R2).

Run with the stack up:  uv run pytest -m integration tools/tests/test_basyx_smoke.py
"""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest
from basyx.aas import model
from basyx.aas.adapter.json import json_serialization

from vf_common import ids

BASE = os.environ.get("VF_AAS_ENV_URL", "http://localhost:8091")
TAG = "SMOKE01"


def _b64(identifier: str) -> str:
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


def _to_json(obj) -> dict:
    return json.loads(json.dumps(obj, cls=json_serialization.AASToJsonEncoder))


@pytest.mark.integration
def test_sdk_objects_roundtrip_through_basyx_go():
    sm = model.Submodel(
        id_=ids.submodel_id(TAG, "OperationalData"),
        id_short="OperationalData",
        semantic_id=model.ExternalReference(
            (model.Key(model.KeyTypes.GLOBAL_REFERENCE, ids.concept_description_id("OperationalData")),)),
        submodel_element={
            model.Property("PowerW", model.datatypes.Double, value=42.5),
            model.MultiLanguageProperty("Name", model.MultiLanguageTextType({"en": "Smoke", "de": "Rauch"})),
        },
    )
    aas = model.AssetAdministrationShell(
        id_=ids.aas_id(TAG),
        id_short=TAG,
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE, global_asset_id=ids.asset_id(TAG)),
        submodel={model.ModelReference.from_referable(sm)},
    )
    with httpx.Client(base_url=BASE, timeout=10) as http:
        http.delete(f"/shells/{_b64(aas.id)}")
        http.delete(f"/submodels/{_b64(sm.id)}")
        try:
            assert http.post("/submodels", json=_to_json(sm)).status_code == 201
            assert http.post("/shells", json=_to_json(aas)).status_code == 201

            got = http.get(f"/submodels/{_b64(sm.id)}/submodel-elements/PowerW/$value")
            assert got.status_code == 200 and float(got.json()) == 42.5

            patch = http.patch(f"/submodels/{_b64(sm.id)}/submodel-elements/PowerW/$value", json="99.0")
            assert patch.status_code == 204, patch.text
            assert float(http.get(
                f"/submodels/{_b64(sm.id)}/submodel-elements/PowerW/$value").json()) == 99.0

            shell = http.get(f"/shells/{_b64(aas.id)}").json()
            assert shell["assetInformation"]["globalAssetId"] == ids.asset_id(TAG)
            descriptor = http.get(f"/shell-descriptors/{_b64(aas.id)}")
            assert descriptor.status_code == 200, "registry integration should create a descriptor"
        finally:
            http.delete(f"/shells/{_b64(aas.id)}")
            http.delete(f"/submodels/{_b64(sm.id)}")
