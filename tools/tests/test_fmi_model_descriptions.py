"""All FMI 3.0 model descriptions in the Godot project are schema-valid and internally consistent."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import xmlschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = xmlschema.XMLSchema(ROOT / "tools" / "schemas" / "fmi3" / "fmi3ModelDescription.xsd")
FILES = sorted(p for p in (ROOT / "godot").rglob("modelDescription.xml") if ".godot" not in p.parts)
VAR_TAGS = {"Float64", "Int32", "UInt64", "Boolean", "String"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT / "godot")))
def test_schema_valid(path: Path):
    SCHEMA.validate(path)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT / "godot")))
def test_consistency(path: Path):
    root = ET.parse(path).getroot()
    variables = [v for v in root.find("ModelVariables") if v.tag in VAR_TAGS]
    vrs = [int(v.get("valueReference")) for v in variables]
    names = [v.get("name") for v in variables]
    assert len(vrs) == len(set(vrs)), "value references must be unique"
    assert len(names) == len(set(names)), "variable names must be unique"
    assert sum(v.get("causality") == "independent" for v in variables) == 1
    units = {u.get("name") for u in root.iter("Unit")}
    for v in variables:
        assert not v.get("unit") or v.get("unit") in units, f"undefined unit on {v.get('name')}"
    outputs = {int(v.get("valueReference")) for v in variables if v.get("causality") == "output"}
    listed = {int(o.get("valueReference")) for o in root.find("ModelStructure").iter("Output")}
    assert outputs == listed, "ModelStructure/Output must list exactly the outputs"
    assert root.find("CoSimulation") is not None


def test_found_model_descriptions():
    assert len(FILES) >= 2
