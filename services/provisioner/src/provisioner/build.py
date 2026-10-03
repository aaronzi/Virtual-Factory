"""Orchestrates the AAS build: asset data + generators -> environment -> validation -> AASX / upload."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from vf_common.aas.aasx import to_object_store, write_aasx_per_shell
from vf_common.aas.entities import asset_names
from vf_common.aas.environment import EnvironmentBuilder
from vf_common.aas.templates import TemplateLibrary
from vf_common.historian import HistorianConfig

from . import device_models as dm
from . import time_series as ts
from .fmi import read_model_description
from .interfaces import aid_values, aimc_values
from .interfaces_opcua import device_models, field_types
from .location import layout_positions, location_values
from .models3d import models3d_values

REPO = Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4]))
DATA_ROOT = REPO / "aas" / "data"
# data sets with their own upload target: the plant (main AAS environment) and the supplier environment
# (ADR-0028); `$include` paths are relative to DATA_ROOT in both
DATA_SETS = {"main": DATA_ROOT, "supplier": DATA_ROOT / "supplier"}


@dataclass
class BuildResult:
    environment: dict
    builder: EnvironmentBuilder


def load_yaml(path: Path) -> dict:
    """Loads asset data; `_extends: file` (top level) and `$include: file` (any mapping) merge shared
    fragments (paths relative to aas/data). `$include: file#a.b` merges only the mapping at key path a.b of
    the file (named fragments shared by several assets). Keys next to `$include` override the included
    content."""
    data = yaml.safe_load(path.read_text()) or {}
    base = data.pop("_extends", None)
    data = _resolve_includes(data, DATA_ROOT)
    return deep_merge(load_yaml(DATA_ROOT / base), data) if base else data


def _resolve_includes(node, root: Path):
    if isinstance(node, dict):
        include = node.get("$include")
        rest = {k: _resolve_includes(v, root) for k, v in node.items() if k != "$include"}
        if include:
            file, _, key = include.partition("#")
            fragment = _resolve_includes(yaml.safe_load((root / file).read_text()), root)
            for part in key.split(".") if key else []:
                fragment = fragment[part]
            return deep_merge(fragment, rest)
        return rest
    if isinstance(node, list):
        return [_resolve_includes(v, root) for v in node]
    return node


def deep_merge(base, override, key: str = ""):
    """Recursive merge (override wins). Lists are replaced, except `submodels`, which merge per
    template/idShort."""
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


def load_assets(data_dir: Path, only: set[str] | None = None, blueprints: bool = False) -> list[dict]:
    """Static assets (aas/data/assets); with `blueprints`, also the runtime blueprints (aas/data/blueprints,
    e.g. the workpiece instance AAS created by the MES) for validation - blueprints are never preloaded."""
    paths = sorted((data_dir / "assets").glob("*.yaml"))
    if blueprints:
        paths += sorted((data_dir / "blueprints").glob("*.yaml"))
    specs = [load_yaml(p) for p in paths]
    return [s for s in specs if not only or s["tag"] in only]


class BuildContext:
    """Template library, layout positions and UNS registry, loaded once; builds environments from asset specs
    (used by `build` and at runtime by the MES for workpiece instance AAS and by the supplier portal for batch
    AAS). `data_dir`: data set whose asset names are known to Entity elements (default: the plant's)."""

    def __init__(self, repo: Path = REPO, data_dir: Path | None = None):
        self.repo = repo
        self.library = TemplateLibrary(repo / "aas" / "templates")
        layout = json.loads((repo / "godot" / "config" / "layouts" / "line1.layout.json").read_text())
        self.uns = json.loads((repo / "godot" / "config" / "uns.json").read_text())
        self.historian = HistorianConfig.load(repo / "infra" / "historian.json")
        self.positions = layout_positions(layout)
        capabilities = yaml.safe_load((repo / "aas" / "data" / "capabilities.yaml").read_text())
        self.library.concept_descriptions.update(capability_cds(capabilities))
        # names of all static assets, for BoM nodes referring to assets outside a (runtime) build
        assets = load_assets(repo / "aas" / "data")
        self.names = asset_names(load_assets(data_dir) if data_dir else assets)
        self.field_types = field_types(device_models(repo, assets))  # event fields of the OPC UA interface

    def build(self, specs: list[dict], validate: bool = True) -> BuildResult:
        builder = EnvironmentBuilder(self.library, self.names)
        for spec in specs:
            spec = copy.deepcopy(spec)
            _apply_generators(spec, self, self.positions)
            builder.add_asset(spec)
        env = builder.build()
        if validate:
            to_object_store(env)  # strict validation
        return BuildResult(env, builder)


def build(repo: Path = REPO, only: set[str] | None = None, blueprints: bool = False,
          data_dir: Path | None = None) -> BuildResult:
    data_dir = data_dir or repo / "aas" / "data"
    return BuildContext(repo, data_dir).build(load_assets(data_dir, only, blueprints))


def capability_cds(dictionary: dict) -> dict[str, dict]:
    """Concept descriptions for the capability dictionary (aas/data/capabilities.yaml)."""
    from vf_common import ids
    from vf_common.aas.templates import IEC61360
    from vf_common.aas.values import mlp_value
    cds = {}
    for name, entry in dictionary.items():
        cd_id = f"{ids.ID_BASE}/capability/{name}"
        content = {"modelType": "DataSpecificationIec61360",
                   "preferredName": mlp_value(entry["preferredName"]),
                   "definition": mlp_value(entry["definition"])}
        if len(name) <= 18:
            content["shortName"] = mlp_value({"en": name})
        cds[cd_id] = {"modelType": "ConceptDescription", "id": cd_id, "idShort": name,
                      "isCaseOf": [{"type": "ExternalReference", "keys": [
                          {"type": "GlobalReference",
                           "value": "https://admin-shell.io/idta/SubmodelTemplate/"
                                    "CapabilityDescription/1/0"}]}],
                      "embeddedDataSpecifications": [{
                          "dataSpecification": {"type": "ExternalReference", "keys": [
                              {"type": "GlobalReference", "value": IEC61360}]},
                          "dataSpecificationContent": content}]}
    return cds


def _apply_generators(spec: dict, ctx: BuildContext, positions: dict) -> None:
    tag, library, repo, uns = spec["tag"], ctx.library, ctx.repo, ctx.uns
    generated: dict[str, dict] = {}
    if spec.get("location") is not False and (tag in positions or spec.get("location")):
        pos = spec.get("location") if isinstance(spec.get("location"), list) else positions.get(tag)
        generated["AssetLocation-1.0"] = location_values(tag, pos, spec.get("locationDescription", tag),
                                                         spec.get("locationTime"))
    if spec.get("model3d"):
        generated["Models3D-1.0"] = models3d_values(spec["model3d"])
    device = spec.get("device")
    if device:
        model_path = device["modelDescription"]
        md = read_model_description(repo / model_path)
        library.concept_descriptions.update({cd["id"]: cd for cd in dm.process_value_cds(md)})
        mappings, energy_vars = dm.aimc_mappings(device, md)
        instance = device.get("instance", tag)
        generated["AssetInterfacesDescription-1.1"] = aid_values(
            tag, instance, md, uns, f"{tag} shop-floor data (UNS)", ctx.field_types)
        generated["AssetInterfacesMappingConfiguration-2.0"] = aimc_values(tag, mappings)
        generated["OperationalData-1.0"] = dm.operational_data_values(md, device, energy_vars)
        generated["SimulationModels-1.0"] = dm.simulation_model_values(tag, md, model_path)
        library.concept_descriptions[ts.UTC_TIME] = ts.utc_time_cd()
        generated["TimeSeries-1.1"] = ts.time_series_values(tag, instance, md, ctx.historian)
        if device.get("energy", {}).get("power"):
            generated["EnergyConsumption-1.0"] = dm.energy_dynamic_values(tag, device)
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


def write_outputs(result: BuildResult, out_dir: Path, env_json: Path | None = None,
                  repo: Path = REPO) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.aasx"):
        old.unlink()
    if env_json:
        env_json.parent.mkdir(parents=True, exist_ok=True)
        env_json.write_text(json.dumps(result.environment, indent=1, ensure_ascii=False))
    return write_aasx_per_shell(result.environment, result.builder.files, result.builder.shell_files,
                                repo, out_dir)
