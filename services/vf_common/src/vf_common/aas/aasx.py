"""Validation and AASX packaging of a built environment (basyx-python-sdk, strict)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from basyx.aas import model
from basyx.aas.adapter import aasx
from basyx.aas.adapter.json import json_deserialization


def to_object_store(environment: dict) -> model.DictIdentifiableStore:
    """Strictly deserialises the environment; raises on any metamodel violation."""
    stream = io.StringIO(json.dumps(environment))
    return json_deserialization.read_aas_json_file(stream, failsafe=False)


def write_aasx_per_shell(environment: dict, files: dict[str, str], shell_files: dict[str, set[str]],
                         repo_root: Path, out_dir: Path) -> list[Path]:
    """Writes one AASX per AAS (its submodels, used concept descriptions and supplementary files)."""
    store = to_object_store(environment)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for shell in environment["assetAdministrationShells"]:
        file_store = aasx.DictSupplementaryFileContainer()
        thumb = (shell["assetInformation"].get("defaultThumbnail") or {}).get("path")
        for package_path in sorted(shell_files.get(shell["id"], ())):
            source = repo_root / files[package_path]
            with (_thumbnail(source) if package_path == thumb else open(source, "rb")) as fh:
                file_store.add_file(package_path, fh, _mime(package_path))
        target = out_dir / f"{shell['idShort']}.aasx"
        wanted = set(_package_object_ids(environment, shell))
        objects = model.DictIdentifiableStore(obj for obj in store if obj.id in wanted)
        with aasx.AASXWriter(str(target)) as writer:
            # not write_aas(): it only follows ModelReference semanticIds to concept descriptions, while IDTA
            # templates use GlobalReferences - the package would contain no concept descriptions at all
            writer.write_all_aas_objects("/aasx/data.json", objects, file_store, write_json=True)
        _strip_empty_specific_asset_ids(target)
        written.append(target)
    return written


def _package_object_ids(environment: dict, shell: dict) -> list[str]:
    """The shell, its submodels and every concept description used by them (semantic, list and supplemental ids)."""
    sm_ids = {ref["keys"][0]["value"] for ref in shell.get("submodels", [])}
    submodels = [sm for sm in environment["submodels"] if sm["id"] in sm_ids]
    used: set[str] = set()
    _collect_ids(submodels, used)
    cd_ids = [cd["id"] for cd in environment.get("conceptDescriptions", []) if cd["id"] in used]
    return [shell["id"], *sorted(sm_ids), *cd_ids]


def _collect_ids(node, ids: set[str]) -> None:
    if isinstance(node, dict):
        for key in ("semanticId", "semanticIdListElement"):
            if node.get(key):
                ids.update(k["value"] for k in node[key].get("keys", []))
        for ref in node.get("supplementalSemanticIds") or []:
            ids.update(k["value"] for k in ref.get("keys", []))
        for value in node.values():
            _collect_ids(value, ids)
    elif isinstance(node, list):
        for value in node:
            _collect_ids(value, ids)


def _strip_empty_specific_asset_ids(package: Path) -> None:
    """basyx-python-sdk 2.2 serialises Entities with `"specificAssetIds": []`, which violates the V3.0 JSON schema
    (minItems 1) and is rejected by aas-test-engines. Removes the empty arrays from the JSON parts."""
    with zipfile.ZipFile(package) as src:
        entries = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in entries:
            if info.filename.endswith(".json"):
                data = json.dumps(_drop_empty(json.loads(data)), ensure_ascii=False).encode()
            dst.writestr(info, data)


def _drop_empty(node):
    if isinstance(node, dict):
        return {k: _drop_empty(v) for k, v in node.items() if not (k == "specificAssetIds" and v == [])}
    if isinstance(node, list):
        return [_drop_empty(v) for v in node]
    return node


def _thumbnail(path: Path, width: int = 480) -> io.BytesIO:
    """Downscaled PNG for AAS thumbnails (review renders are 1200 px wide)."""
    img = Image.open(path)
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


def _mime(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].lower()
    return {"png": "image/png", "pdf": "application/pdf", "glb": "model/gltf-binary", "xml": "application/xml",
            "json": "application/json"}.get(suffix, "application/octet-stream")
