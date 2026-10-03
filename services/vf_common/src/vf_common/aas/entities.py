"""Names of Entity elements (e.g. the nodes of IDTA HierarchicalStructures / bills of material).

The template's displayName and description of a repeated Entity ("Node", "Entry Node") say nothing about the
instance, so the template engine drops them (unless the data gives `_displayName` / `_description`) and this
post-pass names every Entity after the asset it represents: displayName and description of the asset whose
globalAssetId the Entity carries. Entities without a known asset (e.g. an ISA-95 area, a part without AAS)
get their idShort split into words, unless the data names them explicitly.
"""

from __future__ import annotations

import re
from typing import Iterator

from .. import ids

Names = dict[str, dict]  # globalAssetId -> {"displayName": [...], "description": [...]} (AAS JSON MLP lists)


def asset_names(specs: list[dict]) -> Names:
    """Name index of asset specs (aas/data format): globalAssetId -> displayName/description as AAS JSON."""
    out: Names = {}
    for spec in specs:
        gid = spec.get("globalAssetId") or ids.asset_id(spec["tag"])
        out[gid] = {key: _mlp(spec[key]) for key in ("displayName", "description") if spec.get(key)}
    return out


def name_entities(submodels: list[dict], names: Names) -> None:
    """Fills displayName (and a missing description) of all Entity elements in place."""
    for entity in _entities(submodels):
        known = names.get(entity.get("globalAssetId", ""), {})
        if not entity.get("displayName"):
            entity["displayName"] = known.get("displayName") or [
                {"language": "en", "text": _words(entity.get("idShort", ""))}]
        if not entity.get("description") and known.get("description"):
            entity["description"] = known["description"]


def _entities(node) -> Iterator[dict]:
    if isinstance(node, dict):
        if node.get("modelType") == "Entity":
            yield node
        for value in node.values():
            yield from _entities(value)
    elif isinstance(node, list):
        for value in node:
            yield from _entities(value)


def _mlp(texts: dict | str) -> list[dict]:
    texts = texts if isinstance(texts, dict) else {"en": texts}
    return [{"language": lang, "text": str(text)} for lang, text in texts.items()]


def _words(id_short: str) -> str:
    """"FinalAssembly" -> "Final Assembly", "ScrewM5x16" -> "Screw M5x16"."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", id_short) or id_short
