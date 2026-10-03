#!/usr/bin/env python3
"""Prints the element tree of a submodel template (IDTA or custom) with types and cardinalities.

Usage: uv run tools/aas_template_tree.py <TemplateName-ver> [max_depth] [--desc]
       uv run tools/aas_template_tree.py --list
"""

import sys
from pathlib import Path

from vf_common.aas.instantiate import _cardinality
from vf_common.aas.templates import TemplateLibrary

lib = TemplateLibrary(Path(__file__).resolve().parent.parent / "aas" / "templates")


def walk(e: dict, depth: int, max_depth: int, desc: bool) -> None:
    if depth > max_depth:
        return
    vt = e.get("valueType") or e.get("typeValueListElement") or ""
    text = ""
    if desc and e.get("description"):
        text = "  # " + next((d["text"] for d in e["description"] if d["language"] == "en"), "")[:100]
    print("  " * depth + f"{e.get('idShort', '[item]')} <{e['modelType']}{':' + vt if vt else ''}> "
          f"{_cardinality(e)}{text}")
    children = (e.get("value") if isinstance(e.get("value"), list) else []) + (e.get("statements") or [])
    for child in children:
        walk(child, depth + 1, max_depth, desc)


if sys.argv[1] == "--list":
    print("\n".join(sorted(lib.templates)))
else:
    t = lib.get(sys.argv[1])
    print(t["idShort"], t["semanticId"]["keys"][0]["value"])
    depth = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 99
    for el in t["submodelElements"]:
        walk(el, 1, depth, "--desc" in sys.argv)
