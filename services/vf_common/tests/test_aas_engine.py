"""Unit tests of the template engine (instantiation, custom templates, environment building)."""

import base64
import json

import pytest

from vf_common import ids
from vf_common.aas.aasx import to_object_store
from vf_common.aas.environment import EnvironmentBuilder
from vf_common.aas.instantiate import _cardinality, instantiate
from vf_common.aas.templates import compile_custom_template
from vf_common.aas.values import convert_property_value, mlp_value


def _q(card):
    return [{"type": "SMT/Cardinality", "valueType": "xs:string", "value": card}]


TEMPLATE = {
    "modelType": "Submodel", "id": "urn:tmpl", "idShort": "Demo", "kind": "Template",
    "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": "urn:demo"}]},
    "administration": {"version": "1", "revision": "0"},
    "submodelElements": [
        {"modelType": "Property", "idShort": "Name", "valueType": "xs:string", "qualifiers": _q("One")},
        {"modelType": "Property", "idShort": "Optional", "valueType": "xs:int",
         "qualifiers": _q("ZeroToOne")},
        {"modelType": "MultiLanguageProperty", "idShort": "Title", "qualifiers": _q("One")},
        {"modelType": "SubmodelElementCollection", "idShort": "Item__00__", "qualifiers": _q("ZeroToMany"),
         "value": [{"modelType": "Property", "idShort": "Value", "valueType": "xs:double",
                    "qualifiers": _q("One")}]},
        {"modelType": "SubmodelElementList", "idShort": "Entries",
         "typeValueListElement": "SubmodelElementCollection",
         "qualifiers": _q("ZeroToOne"),
         "value": [{"modelType": "SubmodelElementCollection", "idShort": "Entry",
                    "value": [{"modelType": "Property", "idShort": "Flag", "valueType": "xs:boolean"}]}]},
        {"modelType": "ReferenceElement", "idShort": "Link", "qualifiers": _q("ZeroToOne")},
        {"modelType": "Blob", "idShort": "Data", "contentType": "application/json",
         "qualifiers": _q("ZeroToOne")},
    ],
}


def _resolver(key):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": key.removeprefix("global:")}]}


def test_instantiate_fills_expands_and_prunes():
    res = instantiate(TEMPLATE, {
        "Name": "n1", "Title": {"en": "T", "de": "T"},
        "Item": [{"Value": 1.5}, {"_idShort": "Special", "Value": 2}],
        "Entries": [{"Flag": True}, {"Flag": False}],
        "Link": {"ref": "global:urn:x"}, "Data": {"contentType": "application/json", "value": {"a": 1}},
        "+Extra": {"valueType": "xs:double", "value": 3.0, "semanticId": "urn:extra"},
    }, "urn:sm", _resolver)
    els = {e["idShort"]: e for e in res.submodel["submodelElements"]}
    assert res.submodel["kind"] == "Instance" and res.submodel["administration"]["templateId"] == "urn:tmpl"
    assert "Optional" not in els, "unfilled optional element pruned"
    assert {"Item01", "Special"} <= set(els), "placeholder expanded, _idShort respected"
    assert all("idShort" not in item for item in els["Entries"]["value"]), "AASd-120"
    assert els["Entries"]["value"][1]["value"][0]["value"] == "false"
    assert els["Link"]["value"]["keys"][0]["value"] == "urn:x"
    assert json.loads(base64.b64decode(els["Data"]["value"])) == {"a": 1}
    assert els["Extra"]["semanticId"]["keys"][0]["value"] == "urn:extra"
    assert not any("qualifiers" in e for e in els.values()), "template qualifiers removed"
    assert res.missing == [] and res.unknown == []


def test_missing_mandatory_and_unknown_keys_are_reported():
    res = instantiate(TEMPLATE, {"Nme": "typo"}, "urn:sm", _resolver)
    assert "Demo.Name" in res.missing and "Demo.Title" in res.missing
    assert res.unknown == ["Demo.Nme"]


def test_cardinality_variants():
    assert _cardinality({"qualifiers": [{"type": "Multiplicity", "value": "ZeroToOne"}]}) == "ZeroToOne"
    assert _cardinality(
        {"qualifiers": [{"type": "SMT/SMT/Cardinality", "value": "ZerotoMany"}]}) == "ZeroToMany"
    assert _cardinality({}) == "One"


def test_values():
    assert convert_property_value("xs:boolean", 1) == "true"
    assert convert_property_value("xs:double", 2.5) == "2.5"
    with pytest.raises(ValueError):
        mlp_value({"en": "a", "b c": None})  # unquoted comma in YAML flow mapping


def test_custom_template_compiles_with_concept_descriptions():
    template, cds = compile_custom_template({
        "name": "Mini", "version": "1", "revision": "0", "description": {"en": "d", "de": "d"},
        "elements": [{"idShort": "Power", "valueType": "xs:double", "unit": "W",
                      "preferredName": {"en": "power", "de": "Leistung"}}]})
    assert template["submodelElements"][0]["qualifiers"][0]["value"] == "One"
    content = cds[0]["embeddedDataSpecifications"][0]["dataSpecificationContent"]
    assert content["unit"] == "W" and content["dataType"] == "REAL_MEASURE"
    assert cds[0]["id"] == template["submodelElements"][0]["semanticId"]["keys"][0]["value"]


class _Library:
    def __init__(self):
        self.concept_descriptions = {}

    def get(self, name):
        return json.loads(json.dumps(TEMPLATE))

    def concept_descriptions_for(self, tree):
        return []


def test_environment_builder_resolves_element_references_and_validates():
    builder = EnvironmentBuilder(_Library())
    builder.add_asset({"tag": "T1", "idShort": "T1", "derivedFrom": "T0", "submodels": [
        {"template": "Demo-1.0", "values": {"Name": "${asset:T1}", "Title": "x", "Item": [{"Value": 1}],
                                            "Link": {"ref": "sm:T1/Demo#Item01.Value"}}}]})
    env = builder.build()
    sm = env["submodels"][0]
    name = next(e for e in sm["submodelElements"] if e["idShort"] == "Name")
    link = next(e for e in sm["submodelElements"] if e["idShort"] == "Link")
    assert name["value"] == ids.asset_id("T1")
    assert [k["type"] for k in link["value"]["keys"]] == ["Submodel", "SubmodelElementCollection", "Property"]
    assert env["assetAdministrationShells"][0]["derivedFrom"]["keys"][0]["value"] == ids.aas_id("T0")
    to_object_store(env)  # strict metamodel validation


def test_assets_of_another_organisation_get_ids_in_its_namespace():
    base = "https://virtual-factory.example/druckguss-pfalz/ids"
    builder = EnvironmentBuilder(_Library())
    for tag, derived in (("TYPE", None), ("LOT1", "TYPE")):
        builder.add_asset({"tag": tag, "idShort": tag, "idBase": base, "derivedFrom": derived, "submodels": [
            {"template": "Demo-1.0", "values": {"Name": "${aas:TYPE}", "Title": "x",
                                                "Link": {"ref": "aas:TYPE"}}}]})
    env = builder.build()
    lot = env["assetAdministrationShells"][1]
    assert lot["id"] == f"{base}/aas/LOT1"
    assert lot["assetInformation"]["globalAssetId"] == f"{base}/asset/LOT1"
    assert lot["derivedFrom"]["keys"][0]["value"] == f"{base}/aas/TYPE"
    sm = env["submodels"][1]
    assert sm["id"] == f"{base}/sm/LOT1/Demo/1"
    assert {e["idShort"]: e.get("value") for e in sm["submodelElements"]}["Name"] == f"{base}/aas/TYPE"
    to_object_store(env)
