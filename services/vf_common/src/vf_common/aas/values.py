"""Conversion of plain (YAML) values into AAS V3.0 JSON value representations."""

from __future__ import annotations

import datetime as dt
import mimetypes
import re
from typing import Any

DEFAULT_LANG = "en"
LANG_TAG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
MIME_OVERRIDES = {".glb": "model/gltf-binary", ".xml": "application/xml", ".bpmn": "application/bpmn+xml",
                  ".aasx": "application/asset-administration-shell-package"}


def convert_property_value(value_type: str, value: Any) -> str:
    """AAS JSON carries all property values as strings in XSD lexical form."""
    if value is None:
        return ""
    if value_type == "xs:boolean":
        return "true" if value in (True, "true", "True", 1, "1") else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if value_type in ("xs:double", "xs:float", "xs:decimal") and isinstance(value, (int, float)):
        return repr(float(value)) if isinstance(value, float) else str(value)
    return str(value)


def mlp_value(value: Any) -> list[dict]:
    """'text' -> [{en: text}], {en: .., de: ..} -> list of LangStrings."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if not str(k).startswith("_")}  # _idShort etc. are overrides
        bad = [lang for lang in value if not LANG_TAG.match(str(lang))]
        if bad or any(text is None for text in value.values()):
            raise ValueError(f"invalid multi-language value {value!r} (quote texts containing ',' or ':')")
        return [{"language": lang, "text": str(text)} for lang, text in value.items()]
    return [{"language": DEFAULT_LANG, "text": str(value)}]


def file_value(value: Any) -> dict:
    """'path' or {value, contentType} -> File element fields."""
    if isinstance(value, dict):
        path = value["value"]
        mime = value.get("contentType")
    else:
        path, mime = str(value), None
    if not mime:
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        mime = MIME_OVERRIDES.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    return {"value": path, "contentType": mime}
