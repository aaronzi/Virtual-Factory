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
    """Every FMI output of every device is described in the AID and mapped by the AIMC."""
    env = result.environment
    specs = {p.stem: p for p in (REPO / "aas" / "data" / "assets").glob("*.yaml")}
    from provisioner.build import load_yaml
    for tag, path in specs.items():
        device = load_yaml(path).get("device")
        if not device:
            continue
        outputs = {v.name for v in read_model_description(REPO / device["modelDescription"]).by_causality("output")}
        aid = _sm(env, tag, "AssetInterfacesDescription")
        interface = aid["submodelElements"][0]
        meta = next(e for e in interface["value"] if e["idShort"] == "InteractionMetadata")
        props = next(e for e in meta["value"] if e["idShort"] == "properties")
        assert {p["idShort"] for p in props["value"]} == outputs, tag
        aimc = _sm(env, tag, "AssetInterfacesMappingConfiguration")
        configs = aimc["submodelElements"][0]["value"]
        sources = {_child(_child(c, "Sources")["value"][0], "SourceId")["value"] for c in configs}
        assert sources == outputs, tag


def test_aasx_packages_are_conformant(result, tmp_path: Path):
    for path in write_outputs(result if not _has_blueprints(result) else build(), tmp_path):
        with open(path, "rb") as fh:
            check = aas_file.check_aasx_file(fh)
        assert check.ok(), f"{path.name}: " + "\n".join(line for line in check.to_lines() if "\x1b[91m" in line)
        with zipfile.ZipFile(path) as package:
            data = json.loads(package.read("aasx/data.json"))
        assert data.get("conceptDescriptions"), f"{path.name}: concept descriptions must be packaged"


def _child(el: dict, id_short: str) -> dict:
    return next(e for e in el["value"] if e.get("idShort") == id_short)


def _has_blueprints(result) -> bool:
    return any(s["id"].endswith("WP_PC3280_2026_000123") for s in result.environment["assetAdministrationShells"])


def test_environment_json_roundtrip(result):
    assert json.loads(json.dumps(result.environment))["assetAdministrationShells"]
