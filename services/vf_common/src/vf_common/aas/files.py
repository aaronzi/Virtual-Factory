"""File elements of a submodel (for uploading their content as attachments: MES, supplier portal)."""

from __future__ import annotations


def file_elements(elements: list[dict], prefix: str = "", in_list: bool = False):
    """(idShort path, element) of every File element; SubmodelElementList items are addressed as name[i]."""
    for index, element in enumerate(elements):
        if in_list:
            path = f"{prefix}[{index}]"
        else:
            path = f"{prefix}.{element['idShort']}" if prefix else element["idShort"]
        kind = element.get("modelType")
        if kind == "File":
            yield path, element
        elif kind in ("SubmodelElementCollection", "SubmodelElementList"):
            yield from file_elements(element.get("value") or [], path, kind == "SubmodelElementList")
