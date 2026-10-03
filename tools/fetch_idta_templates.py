#!/usr/bin/env python3
"""Vendors the IDTA submodel templates used by the Virtual Factory (and their concept descriptions).

Source: IDTA submodel template repository (an AAS API V3 server):
    https://smt-repo.admin-shell-io.com/api/v3.0/submodels
    https://smt-repo.admin-shell-io.com/api/v3.0/concept-descriptions
Output: aas/templates/idta/<Name>-<version>.json, aas/templates/idta/concept_descriptions.json,
        aas/templates/idta/manifest.json

Usage: uv run tools/fetch_idta_templates.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

BASE = "https://smt-repo.admin-shell-io.com/api/v3.0"
OUT = Path(__file__).resolve().parent.parent / "aas" / "templates" / "idta"
ID = "https://admin-shell.io/idta/SubmodelTemplate/"

# local name -> template submodel id in the repository
TEMPLATES = {
    "Nameplate-3.0": ID + "DigitalNameplate/3/0",
    "TechnicalData-2.0": ID + "TechnicalData/2/0",
    "ContactInformations-1.0": ID + "ContactInformation/1/0",
    "HandoverDocumentation-2.0": ID + "HandoverDocumentation/2/0",
    "CarbonFootprint-1.0": ID + "CarbonFootprint/1/0",
    "AssetInterfacesDescription-1.1": ID + "AssetInterfacesDescription/1/1",
    "AssetInterfacesMappingConfiguration-2.0": ID + "AssetInterfacesMappingConfiguration/2/0",
    "TimeSeries-1.1": ID + "TimeSeries/1/1",
    "SimulationModels-1.0": ID + "SimulationModels/1/0",
    "Models3D-1.0": ID + "ProvisionOf3DModels/1/0",
    "AssetLocation-1.0": ID + "DataModelforAssetLocation/1/0",
    "HierarchicalStructures-1.1": ID + "HierarchicalStructuresBoM/1/1",
    "CapabilityDescription-1.0": ID + "CapabilityDescription/1/0",
    "ControlComponentType-2.0": ID + "ControlComponentType/2/0",
    "ControlComponentInstance-2.0": ID + "ControlComponent/Instance/2/0",
    "ProcessParameters-1.0": "https://admin-shell-io/idta/SubmodelTemplate/ProcessParameters/1/0",
    "ExecutedProcesses-1.0": "https://admin-shell.io/idta/ExecutedProcesses/1/0",
    "MeasurementValue-1.0": ID + "measurementValue/1/0",
    "DppMetadata-1.0": ID + "dppMetadata/1/0",
    "FunctionalSafety-1.0": ID + "FunctionalSafety/1/0",
    "Reliability-1.0": ID + "Reliability/1/0",
    "PowerDriveTrainSizing-1.0": ID + "SizingofPowerDriveTrains/1/0",
    "MaintenanceInstructions-1.0": ID + "MaintenanceInstructions/1/0",
    "SoftwareNameplate-1.0": ID + "SoftwareNameplate/1/0",
    "DataRetentionPolicies-1.0": "https://admin-shell.io/idta/DataRetentionPolicies/1/0",
    "ProcessVariablesForManufacturingKPICalculation-1.0":
        ID + "ProcessVariablesForManufacturingKPICalculation/1/0",
    "ProductionCalendar-1.0": ID + "ProductionCalendar/1/0",
    "CompanyData-1.0": ID + "CompanyData/1/0",
    # Digital Battery Passport templates: reference for the generic product variants in aas/templates/custom
    "DBP-MaterialComposition-1.0":
        "urn:samm:io.admin-shell.idta.batterypass.material_composition:1.0.0#MaterialComposition/submodel",
    "DBP-Circularity-1.0": "urn:samm:io.admin-shell.idta.batterypass.circularity:1.0.0#Circularity/submodel",
}


def semantic_ids(node, found: set[str]) -> set[str]:
    if isinstance(node, dict):
        for key in ("semanticId",):
            ref = node.get(key)
            if ref:
                found.update(k["value"] for k in ref.get("keys", []))
        for v in node.values():
            semantic_ids(v, found)
    elif isinstance(node, list):
        for v in node:
            semantic_ids(v, found)
    return found


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as http:
        all_sms = http.get(f"{BASE}/submodels", params={"limit": 1000}).json()["result"]
        all_cds = http.get(f"{BASE}/concept-descriptions", params={"limit": 10000}).json()["result"]
    by_id = {sm["id"]: sm for sm in all_sms}
    cds_by_id = {cd["id"]: cd for cd in all_cds}
    manifest, used = {}, set()
    for name, sm_id in TEMPLATES.items():
        sm = by_id[sm_id]
        (OUT / f"{name}.json").write_text(json.dumps(sm, indent=1, ensure_ascii=False))
        sem = sm.get("semanticId", {}).get("keys", [{}])[0].get("value", "")
        manifest[name] = {"id": sm_id, "idShort": sm.get("idShort"), "semanticId": sem,
                          "version": (sm.get("administration") or {}).get("version"),
                          "revision": (sm.get("administration") or {}).get("revision")}
        used |= semantic_ids(sm, set())
    cds = [cds_by_id[i] for i in sorted(used) if i in cds_by_id]
    (OUT / "concept_descriptions.json").write_text(json.dumps(cds, indent=1, ensure_ascii=False))
    (OUT / "manifest.json").write_text(json.dumps(
        {"source": BASE, "fetched": dt.date.today().isoformat(), "templates": manifest}, indent=1))
    print(f"{len(manifest)} templates, {len(cds)} of {len(used)} referenced concept descriptions available")


if __name__ == "__main__":
    main()
