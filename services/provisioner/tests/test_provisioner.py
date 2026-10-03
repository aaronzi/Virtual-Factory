"""Provisioner: the complete static AAS model builds, validates and stays consistent with the FMI models."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from aas_test_engines import file as aas_file

from provisioner.build import REPO, build, write_outputs
from provisioner.fmi import read_model_description


@pytest.fixture(scope="module")
def result():
    return build(blueprints=True)


def _sm(env: dict, tag: str, id_short: str) -> dict:
    sm_id = f"https://virtual-factory.example/ids/sm/{tag}/{id_short}/"
    return next(s for s in env["submodels"] if s["id"].startswith(sm_id))


def test_build_has_no_unknown_or_missing_values(result):
    assert result.builder.report.unknown == {}, "keys that do not exist in the templates"
    assert result.builder.report.missing == {}, "mandatory template elements without value"


def test_every_shell_references_existing_submodels(result):
    env = result.environment
    sm_ids = {s["id"] for s in env["submodels"]}
    for shell in env["assetAdministrationShells"]:
        for ref in shell.get("submodels", []):
            assert ref["keys"][0]["value"] in sm_ids


def test_device_interfaces_match_fmi_outputs(result):
    """The AID describes every FMI output (the interface is unchanged); the AIMC maps exactly what the AAS
    stores (slim AAS rule, ADR-0019): discrete outputs + energy/hours/state variables; the TimeSeries record
    lists every output (history in the historian)."""
    from provisioner.build import load_yaml
    from provisioner.device_models import is_state_value
    env = result.environment
    for tag, path in {p.stem: p for p in (REPO / "aas" / "data" / "assets").glob("*.yaml")}.items():
        device = load_yaml(path).get("device")
        if not device:
            continue
        md = read_model_description(REPO / device["modelDescription"])
        outputs = {v.name for v in md.by_causality("output")}
        stored = {v.name for v in md.by_causality("output") if is_state_value(v)}
        mapped_extra = {device.get("operatingHours"), (device.get("state") or {}).get("variable"),
                        *(device.get("energy") or {}).values()} - {None}
        assert {p["idShort"] for p in _aid_properties(env, tag)} == outputs, tag
        configs = _sm(env, tag, "AssetInterfacesMappingConfiguration")["submodelElements"][0]["value"]
        sources = {_child(_child(c, "Sources")["value"][0], "SourceId")["value"] for c in configs}
        assert sources == stored | mapped_extra, tag
        values = _child(_sm(env, tag, "OperationalData")["submodelElements"], "ProcessValues")["value"]
        assert {v["idShort"] for v in values} == stored - set((device.get("energy") or {}).values()) \
            - {device.get("operatingHours")}, tag
        metadata = _child(_sm(env, tag, "TimeSeries")["submodelElements"], "Metadata")
        record = [e["idShort"] for e in _child(metadata, "Record")["value"]]
        assert record == ["Time", *[v.name for v in md.by_causality("output")]], tag


def test_time_series_links_the_historian(result):
    from provisioner.time_series import UTC_TIME
    ts = _sm(result.environment, "RB01", "TimeSeries")["submodelElements"]
    record = _child(_child(ts, "Metadata")["value"], "Record")["value"]
    assert record[0]["valueType"] == "xs:dateTime" and record[0]["semanticId"]["keys"][0]["value"] == UTC_TIME
    q1 = next(e for e in record if e["idShort"] == "q1")
    assert q1["semanticId"]["keys"][0]["value"].endswith("/cd/fmi/UR5e/q1") and "value" not in q1
    segment = _child(_child(ts, "Segments")["value"], "Historian")["value"]
    values = {e["idShort"]: e.get("value") for e in segment}
    assert values["Endpoint"] == "http://localhost:8181/api/v3/query_sql?db=vf&format=json"
    assert values["Query"].startswith('SELECT "time", "q1"') and 'FROM "rb01"' in values["Query"]
    energy = _sm(result.environment, "RB01", "EnergyConsumption")["submodelElements"]
    assert _child(energy, "TimeSeries")["value"]["keys"][0]["value"].endswith("/RB01/TimeSeries/1")


def _aid_properties(env: dict, tag: str) -> list[dict]:
    interface = _sm(env, tag, "AssetInterfacesDescription")["submodelElements"][0]
    meta = next(e for e in interface["value"] if e["idShort"] == "InteractionMetadata")
    return next(e for e in meta["value"] if e["idShort"] == "properties")["value"]


def test_aasx_packages_are_conformant(result, tmp_path: Path):
    for path in write_outputs(result if not _has_blueprints(result) else build(), tmp_path):
        with open(path, "rb") as fh:
            check = aas_file.check_aasx_file(fh)
        assert check.ok(), f"{path.name}: " + "\n".join(
            line for line in check.to_lines() if "\x1b[91m" in line)
        with zipfile.ZipFile(path) as package:
            data = json.loads(package.read("aasx/data.json"))
        assert data.get("conceptDescriptions"), f"{path.name}: concept descriptions must be packaged"


def _child(el: dict | list, id_short: str) -> dict:
    return next(e for e in (el["value"] if isinstance(el, dict) else el) if e.get("idShort") == id_short)


def _has_blueprints(result) -> bool:
    return any(s["id"].endswith("WP_PC3280_2026_000123")
               for s in result.environment["assetAdministrationShells"])


def test_environment_json_roundtrip(result):
    assert json.loads(json.dumps(result.environment))["assetAdministrationShells"]


NUMERIC = {"xs:double", "xs:float", "xs:decimal", "xs:int", "xs:integer", "xs:long", "xs:unsignedInt",
           "xs:short"}


def _data_elements(node):
    if isinstance(node, dict):
        if node.get("modelType") in ("Property", "Range"):
            yield node
        for value in node.values():
            yield from _data_elements(value)
    elif isinstance(node, list):
        for value in node:
            yield from _data_elements(value)


def test_concept_descriptions_carry_semantics_and_units(result):
    """Every data element resolves to a concept description; measures have a unit there (not in the text)."""
    env = result.environment
    cds = {cd["id"]: cd["embeddedDataSpecifications"][0]["dataSpecificationContent"]
           for cd in env["conceptDescriptions"] if cd.get("embeddedDataSpecifications")}
    problems = []
    for el in _data_elements(env["submodels"]):
        sem = (el.get("semanticId") or {}).get("keys", [{}])[0].get("value")
        content = cds.get(sem)
        if content is None:
            problems.append(f"{el.get('idShort')}: no concept description for {sem}")
            continue
        if content.get("dataType", "").endswith("MEASURE") and not content.get("unit"):
            problems.append(f"{el.get('idShort')}: measure without unit ({sem})")
        if el.get("valueType") in NUMERIC and content.get("dataType", "").startswith("STRING"):
            problems.append(f"{el.get('idShort')}: numeric value with {content['dataType']} concept")
        text = " ".join(d["text"] for d in el.get("description") or [])
        if any(f"[{u}]" in text for u in ("mm", "m", "kg", "s", "°C", "bar", "N", "W", "V", "A")):
            problems.append(f"{el.get('idShort')}: unit in description text")
    assert not problems, "\n".join(sorted(set(problems))[:20])
