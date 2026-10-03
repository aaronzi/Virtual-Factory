"""InfluxDB line protocol encoding of UNS telemetry samples.

    <table>,session=<id> <field>=<value>[,<field>=<value>...] <unix ms>

Field types follow the FMI type of the variable, so a field never changes its type (InfluxDB rejects that):
Float64 -> float, Int32/UInt64 -> integer (`i`), Boolean -> boolean, String -> string. Non-finite floats and
nulls are skipped."""

from __future__ import annotations

import math
from datetime import datetime, timezone


def _escape(text: str, chars: str) -> str:
    out = text.replace("\\", "\\\\")
    for ch in chars:
        out = out.replace(ch, "\\" + ch)
    return out


def measurement(name: str) -> str:
    return _escape(name, ", ")


def key(name: str) -> str:
    """Tag key, tag value or field key."""
    return _escape(name, ",= ")


def field_value(fmi_type: str, value) -> str | None:
    """Line-protocol field value for a JSON value of an FMI variable; None = do not write."""
    if value is None:
        return None
    try:
        if fmi_type == "Boolean":
            return "true" if value in (True, 1, "true", "1") else "false"
        if fmi_type in ("Int32", "UInt64"):
            return f"{int(value)}i"
        if fmi_type == "Float64":
            number = float(value)
            return repr(number) if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def line(table: str, tags: dict[str, str], fields: dict[str, str], ts_ms: int) -> str:
    tag_part = "".join(f",{key(k)}={key(v)}" for k, v in sorted(tags.items()) if v)
    field_part = ",".join(f"{key(k)}={v}" for k, v in fields.items())
    return f"{measurement(table)}{tag_part} {field_part} {ts_ms}"


def ts_millis(iso: str) -> int:
    """ISO 8601 UTC timestamp ("2026-10-03T13:36:54.052Z") -> Unix milliseconds."""
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round(parsed.timestamp() * 1000)
