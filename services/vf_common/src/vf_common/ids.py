"""Identifier scheme for all AAS-related identifiers (see docs/architecture, crosscutting concepts).

    https://virtual-factory.example/ids/aas/<assetTag>
    https://virtual-factory.example/ids/asset/<assetTag>
    https://virtual-factory.example/ids/sm/<assetTag>/<Submodel>/<version>
    https://virtual-factory.example/ids/cd/<name>
"""

from __future__ import annotations

import os

ID_BASE = os.environ.get("VF_ID_BASE", "https://virtual-factory.example/ids").rstrip("/")


def aas_id(asset_tag: str) -> str:
    return f"{ID_BASE}/aas/{asset_tag}"


def asset_id(asset_tag: str) -> str:
    return f"{ID_BASE}/asset/{asset_tag}"


def submodel_id(asset_tag: str, submodel: str, version: str = "1") -> str:
    return f"{ID_BASE}/sm/{asset_tag}/{submodel}/{version}"


def concept_description_id(name: str) -> str:
    return f"{ID_BASE}/cd/{name}"


def serial_number(year: int, counter: int, type_code: str = "PC3280") -> str:
    """Workpiece serial number, e.g. PC3280-2026-000123."""
    return f"{type_code}-{year:04d}-{counter:06d}"
