"""Validation and AASX packaging of a built environment (basyx-python-sdk, strict)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from basyx.aas import model
from basyx.aas.adapter import aasx
from basyx.aas.adapter.json import json_deserialization


def to_object_store(environment: dict) -> model.DictObjectStore:
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
        with aasx.AASXWriter(str(target)) as writer:
            writer.write_aas(shell["id"], store, file_store, write_json=True)
        written.append(target)
    return written


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
