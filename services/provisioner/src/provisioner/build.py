"""Orchestrates the AAS build: asset data + generators -> environment -> validation -> AASX / upload."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from vf_common.aas.aasx import to_object_store, write_aasx_per_shell
from vf_common.aas.environment import EnvironmentBuilder
from vf_common.aas.templates import TemplateLibrary

from . import device_models as dm
from .fmi import read_model_description
from .interfaces import aid_values, aimc_values
from .location import layout_positions, location_values
from .models3d import models3d_values

REPO = Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4]))
DATA_ROOT = REPO / "aas" / "data"


@dataclass
class BuildResult:
    environment: dict
    builder: EnvironmentBuilder


def load_yaml(path: Path) -> dict:
    """Loads asset data; `_extends: file` (top level) and `$include: file` (any mapping) merge shared fragments
    (paths relative to aas/data). Keys next to `$include` override the included content."""
    data = yaml.safe_load(path.read_text()) or {}
    base = data.pop("_extends", None)
    data = _resolve_includes(data, DATA_ROOT)
    return deep_merge(load_yaml(DATA_ROOT / base), data) if base else data


def _resolve_includes(node, root: Path):
    if isinstance(node, dict):
        include = node.get("$include")
        rest = {k: _resolve_includes(v, root) for k, v in node.items() if k != "$include"}
        if include:
            return deep_merge(_resolve_includes(yaml.safe_load((root / include).read_text()), root), rest)
        return rest
    if isinstance(node, list):
        return [_resolve_includes(v, root) for v in node]
    return node


def deep_merge(base, override, key: str = ""):
    """Recursive merge (override wins). Lists are replaced, except `submodels`, which merge per template/idShort."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = deep_merge(base.get(k), v, k) if k in base else v
        return out
    if key == "submodels" and isinstance(base, list) and isinstance(override, list):
        return _merge_submodel_lists(base, override)
    return copy.deepcopy(override)


def _merge_submodel_lists(base: list, override: list) -> list:
    out = copy.deepcopy(base)
    for entry in override:
        match = next((s for s in out if s["template"] == entry["template"]
                      and s.get("idShort") == entry.get("idShort")), None)
        if match is None:
            out.append(copy.deepcopy(entry))
        else:
            match["values"] = deep_merge(match.get("values") or {}, entry.get("values") or {})
    return out


def load_assets(data_dir: Path, only: set[str] | None = None) -> list[dict]:
    specs = [load_yaml(p) for p in sorted((data_dir / "assets").glob("*.yaml"))]
    return [s for s in specs if not only or s["tag"] in only]


def build(repo: Path = REPO, only: set[str] | None = None) -> BuildResult:
    library = TemplateLibrary(repo / "aas" / "templates")
    layout = json.loads((repo / "godot" / "config" / "layouts" / "line1.layout.json").read_text())
    uns = yaml.safe_load((repo / "godot" / "config" / "uns.yaml").read_text())
    positions = layout_positions(layout)
    library.concept_descriptions.update(capability_cds(yaml.safe_load((DATA_ROOT / "capabilities.yaml").read_text())))
    builder = EnvironmentBuilder(library)
    for spec in load_assets(repo / "aas" / "data", only):
        _apply_generators(spec, library, repo, uns, positions)
        builder.add_asset(spec)
    env = builder.build()
    to_object_store(env)  # strict validation
    return BuildResult(env, builder)


def capability_cds(dictionary: dict) -> dict[str, dict]:
    """Concept descriptions for the capability dictionary (aas/data/capabilities.yaml)."""
    from vf_common import ids
    from vf_common.aas.templates import IEC61360
    from vf_common.aas.values import mlp_value
    cds = {}
    for name, entry in dictionary.items():
        cd_id = f"{ids.ID_BASE}/capability/{name}"
        content = {"modelType": "DataSpecificationIec61360", "preferredName": mlp_value(entry["preferredName"]),
                   "definition": mlp_value(entry["definition"])}
        if len(name) <= 18:
            content["shortName"] = mlp_value({"en": name})
        cds[cd_id] = {"modelType": "ConceptDescription", "id": cd_id, "idShort": name,
                      "isCaseOf": [{"type": "ExternalReference", "keys": [
                          {"type": "GlobalReference",
                           "value": "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0"}]}],
                      "embeddedDataSpecifications": [{"dataSpecification": {"type": "ExternalReference", "keys": [
                          {"type": "GlobalReference", "value": IEC61360}]}, "dataSpecificationContent": content}]}
    return cds


def _apply_generators(spec: dict, library: TemplateLibrary, repo: Path, uns: dict, positions: dict) -> None:
    tag = spec["tag"]
    generated: dict[str, dict] = {}
    if spec.get("location") is not False and (tag in positions or spec.get("location")):
        pos = spec.get("location") if isinstance(spec.get("location"), list) else positions.get(tag)
        generated["AssetLocation-1.0"] = location_values(tag, pos, spec.get("locationDescription", tag))
    if spec.get("model3d"):
        generated["Models3D-1.0"] = models3d_values(spec["model3d"])
    device = spec.get("device")
    if device:
        model_path = device["modelDescription"]
        md = read_model_description(repo / model_path)
        library.concept_descriptions.update({cd["id"]: cd for cd in dm.process_value_cds(md)})
        mappings, energy_vars = dm.aimc_mappings(device, md)
        instance = device.get("instance", tag)
        generated["AssetInterfacesDescription-1.1"] = aid_values(tag, instance, md, uns, f"{tag} shop-floor data (UNS)")
        generated["AssetInterfacesMappingConfiguration-2.0"] = aimc_values(tag, mappings)
        generated["OperationalData-1.0"] = dm.operational_data_values(md, device, energy_vars)
        generated["SimulationModels-1.0"] = dm.simulation_model_values(tag, md, model_path)
        if device.get("energy", {}).get("power"):
            generated["EnergyConsumption-1.0"] = dm.energy_dynamic_values(tag, device)
            generated["TimeSeries-1.1:PowerTimeSeries"] = dm.time_series_values(tag)
    _merge_generated(spec, generated)


def _merge_generated(spec: dict, generated: dict[str, dict]) -> None:
    submodels = spec.setdefault("submodels", [])
    for key, values in generated.items():
        template, _, id_short = key.partition(":")
        existing = next((s for s in submodels if s["template"] == template
                         and (not id_short or s.get("idShort") == id_short)), None)
        if existing is None:
            entry = {"template": template, "values": values}
            if id_short:
                entry["idShort"] = id_short
            submodels.append(entry)
        else:
            existing["values"] = deep_merge(values, existing.get("values") or {})


def write_outputs(result: BuildResult, out_dir: Path, repo: Path = REPO) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.aasx"):
        old.unlink()
    (repo / "aas" / "build").mkdir(parents=True, exist_ok=True)
    (repo / "aas" / "build" / "environment.json").write_text(json.dumps(result.environment, indent=1, ensure_ascii=False))
    return write_aasx_per_shell(result.environment, result.builder.files, result.builder.shell_files, repo, out_dir)
