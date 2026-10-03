"""Generic HTML rendering of DPP API values (compressed representation: value-only JSON, multi-language
strings as [{language, value}] lists)."""

from __future__ import annotations

import re
from html import escape

MAX_DEPTH = 5
_WORD = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
URL = re.compile(r"^https?://\S+$")


def is_langstring(value) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, dict) and set(v) == {"language", "value"} for v in value)


def pick(value, lang: str) -> str:
    """Text of a multi-language value in `lang` (fallback en, then the first)."""
    if not is_langstring(value):
        return "" if value is None else str(value)
    by_lang = {v["language"][:2]: v["value"] for v in value}
    return by_lang.get(lang) or by_lang.get("en") or value[0]["value"]


def humanize(key: str) -> str:
    return _WORD.sub(" ", key).replace("_", " ").strip().capitalize()


def scalar(value, lang: str) -> str:
    text = pick(value, lang)
    if URL.match(text):
        label = "PDF" if "/attachment" in text else text
        return f'<a href="{escape(text)}">{escape(label)}</a>'
    return escape(text)


def value_html(value, lang: str, depth: int = 0) -> str:
    """Nested definition lists / tables for dicts and lists of the value-only representation."""
    if is_langstring(value) or not isinstance(value, (dict, list)):
        return scalar(value, lang)
    if depth >= MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        rows = "".join(f"<dt>{escape(humanize(k))}</dt><dd>{value_html(v, lang, depth + 1)}</dd>"
                       for k, v in value.items() if v not in (None, "", [], {}))
        return f"<dl>{rows}</dl>"
    if value and all(isinstance(v, dict) for v in value) and _flat(value):
        return table(value, lang)
    items = "".join(f"<li>{value_html(v, lang, depth + 1)}</li>" for v in value)
    return f"<ul>{items}</ul>"


def table(rows: list[dict], lang: str) -> str:
    rows = [_flatten(row) for row in rows]
    columns: list[str] = []
    for row in rows:
        columns += [k for k in row if k not in columns]
    head = "".join(f"<th>{escape(humanize(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{value_html(row.get(c, ''), lang, MAX_DEPTH - 1)}</td>"
                                    for c in columns) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _flat(rows: list[dict]) -> bool:
    """Rows whose values are scalars, language strings or small flat dicts (rendered inline)."""
    return all(not isinstance(v, (dict, list)) or is_langstring(v) or
               (isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()))
               for row in rows for v in row.values())


def _flatten(row: dict) -> dict:
    """Small nested dicts (e.g. MaterialLocation) become columns of their own."""
    out = {}
    for key, value in row.items():
        if isinstance(value, dict):
            out.update({k: v for k, v in value.items() if k not in row})
        else:
            out[key] = value
    return out
