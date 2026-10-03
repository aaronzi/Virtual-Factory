"""Generates the dynamic-data submodels of a device from its FMI model description:
OperationalData (process values with generated concept descriptions), EnergyConsumption (dynamic part),
TimeSeries (power), SimulationModels (ports and model file) and the AIMC mapping list."""

from __future__ import annotations

import re

from vf_common import ids
from vf_common.aas.templates import IEC61360, DATA_TYPES

from .fmi import FmiVariable, ModelDescription

AID_NOTE = "Published via the asset interface (see AssetInterfacesDescription)."


def process_value_cd_id(md: ModelDescription, var: FmiVariable) -> str:
    return f"{ids.ID_BASE}/cd/fmi/{md.model_name}/{var.name}"


def process_value_cds(md: ModelDescription) -> list[dict]:
    """IEC 61360 concept descriptions for every FMI output (name, definition, unit, data type)."""
    cds = []
    for var in md.by_causality("output"):
        content = {"modelType": "DataSpecificationIec61360",
                   "preferredName": [{"language": "en", "text": _human(var.name)}],
                   "definition": [{"language": "en", "text": var.description or f"{_human(var.name)} of {md.model_name}"}],
                   "dataType": DATA_TYPES.get(var.xsd_type, "STRING")}
        if var.unit:
            content["unit"] = var.unit
        elif content["dataType"].endswith("_MEASURE"):  # AASc-3a-009: measures need a unit
            content["dataType"] = content["dataType"].replace("_MEASURE", "_COUNT")
        if len(var.name) <= 18:  # IEC 61360 ShortNameTypeIEC61360
            content["shortName"] = [{"language": "en", "text": var.name}]
        cds.append({"modelType": "ConceptDescription", "id": process_value_cd_id(md, var), "idShort": var.name,
                    "embeddedDataSpecifications": [{"dataSpecification": {"type": "ExternalReference", "keys": [
                        {"type": "GlobalReference", "value": IEC61360}]}, "dataSpecificationContent": content}]})
    return cds


def operational_data_values(md: ModelDescription, device: dict, excluded: set[str]) -> dict:
    values = []
    for var in md.by_causality("output"):
        if var.name in excluded:
            continue
        values.append({"_idShort": var.name, "valueType": var.xsd_type, "value": var.start or _zero(var),
                       "semanticId": process_value_cd_id(md, var), "_description": var.description or var.name})
    state = device.get("state", {})
    vocabulary = ", ".join(f"{k} = {v}" for k, v in (state.get("map") or {}).items())
    out = {"OperatingState": (state.get("map") or {}).get(str(state.get("initial", "")), "Unknown"),
           "OperatingHours": 0.0, "ProcessValues": {"ProcessValue": values}}
    if vocabulary:
        out["StateVocabulary"] = {"en": f"{state['variable']}: {vocabulary}"}
    return out


def energy_dynamic_values(tag: str, device: dict) -> dict:
    out = {"ActualPower": 0.0, "EnergyConsumed": 0.0, "PowerTimeSeries": {"ref": f"sm:{tag}/PowerTimeSeries"}}
    if device.get("energy", {}).get("air"):
        out["CompressedAir"] = {"AirConsumed": 0.0}
    return out


def aimc_mappings(device: dict, md: ModelDescription) -> tuple[list[tuple], set[str]]:
    """(FMI output, sink path, lookup) for all outputs; returns the mapping list and the energy-mapped outputs."""
    energy = device.get("energy", {})
    targets = {energy.get("power"): "EnergyConsumption#ActualPower",
               energy.get("energy"): "EnergyConsumption#EnergyConsumed",
               energy.get("air"): "EnergyConsumption#CompressedAir.AirConsumed",
               device.get("operatingHours"): "OperationalData#OperatingHours"}
    targets.pop(None, None)
    mappings = [(var, sink, None) for var, sink in targets.items()]
    state = device.get("state")
    if state:
        mappings.append((state["variable"], "OperationalData#OperatingState", state.get("map")))
    for var in md.by_causality("output"):
        if var.name not in targets:
            mappings.append((var.name, f"OperationalData#ProcessValues.{var.name}", None))
    return mappings, set(targets)


def time_series_values(tag: str) -> dict:
    return {"Metadata": {"Name": {"en": f"Electrical power {tag}", "de": f"Elektrische Leistung {tag}"},
                         "Description": {"en": "Power samples written by the edge data bridge (1 Hz, session).",
                                         "de": "Leistungswerte der Edge-Datenbrücke (1 Hz, Sitzung)."},
                         "Record": {"Time": [{"value": 0, "_idShort": "Time"}],
                                    "+Power": {"valueType": "xs:double", "value": 0,
                                               "semanticId": f"{ids.ID_BASE}/cd/EnergyConsumption/ActualPower/1/0"}}},
            "Segments": {"InternalSegment": [{"_idShort": "Session", "Name": {"en": "Current session"},
                                              "RecordCount": 0, "State": "in progress", "Records": {}}]}}


def simulation_model_values(tag: str, md: ModelDescription, model_path: str) -> dict:
    ports = []
    for causality, title in (("input", "Inputs"), ("output", "Outputs"), ("parameter", "Parameters")):
        variables = [{"_idShort": v.name, "VariableName": v.name, "VariableType": v.type,
                      "VariableCausality": causality, "UnitList": v.unit or "-",
                      **({"VariableDescription": {"en": v.description}} if v.description else {}),
                      **({"Range": f"[{v.min or '-inf'}, {v.max or 'inf'}]"} if v.min or v.max else {})}
                     for v in md.by_causality(causality)]
        if variables:
            ports.append({"_idShort": title, "PortConnectorName": title, "Variable": variables})
    return {"SimulationModel": [{
        "_idShort": md.model_name,
        "Summary": {"en": md.description},
        "SimPurpose": {"PosSimPurpose": [{"value": p} for p in (
            "Virtual commissioning", "Operator training", "Digital twin visualisation", "Energy estimation")],
            "NegSimPurpose": [{"value": "Physics-accurate dynamics (logic and energy level only)"}]},
        "TypeOfModel": [{"value": "Discrete-time behaviour model"}],
        "ScopeOfModel": [{"value": "Logic"}, {"value": "Energy"}],
        "LicenseModel": "Project-internal",
        "EngineeringDomain": [{"value": "Automation"}],
        "Environment": [{"OperatingSystem": "Windows, macOS, Linux", "ToolEnvironment": [{"value": "Godot 4.7"}],
                         "SimulationTool": [{"SimToolName": "Virtual Factory co-simulation master (FMI 3.0 aligned)",
                                             "SolverAndTolerances": {"StepSizeControlNeeded": False,
                                                                     "FixedStepSize": 0.0166667,
                                                                     "StiffSolverNeeded": False,
                                                                     "SolverIncluded": True}}]}],
        "ModelFile": {"ModelFileType": "FMI 3.0 Co-Simulation model description (behaviour implemented in GDScript)",
                      "ModelFileVersion": [{"ModelVersionId": md.version, "DigitalFile": f"repo:{model_path}"}]},
        "ParamMethod": "FMI parameters (start values of the model description, overridden by the line layout)",
        "InitStateMethod": "FMI initialization mode with start values",
        "Ports": {"PortsConnector": ports},
    }]}


def _human(name: str) -> str:
    return re.sub(r"_+", " ", name).strip()


def _zero(var: FmiVariable) -> str:
    return {"Boolean": "false", "String": ""}.get(var.type, "0")
