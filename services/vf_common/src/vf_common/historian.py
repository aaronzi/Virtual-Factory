"""Historian configuration (`infra/historian.json`) and a minimal InfluxDB 3 HTTP client (ADR-0019).

Data model: one table per device (lower-case FMI instance name, the UNS `{device}` segment), one field per FMI
output, tag `session`, timestamp = UNS `ts` (simulation time base, UTC, millisecond precision).

    write  POST {url}/api/v3/write_lp?db={database}&precision=millisecond   (line protocol)
    query  POST {url}/api/v3/query_sql  {"db", "q", "format": "json"}       (SQL, rows as JSON objects)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx


def default_path() -> Path:
    return (Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4]))
            / "infra" / "historian.json")


def quote_ident(name: str) -> str:
    """SQL identifier in double quotes (variable names like `full` or `signal` are SQL keywords)."""
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class HistorianConfig:
    config: dict

    @classmethod
    def load(cls, path: Path | None = None) -> "HistorianConfig":
        return cls(json.loads((path or default_path()).read_text()))

    @property
    def database(self) -> str:
        return self.config["database"]

    @property
    def batch(self) -> dict:
        return self.config["batch"]

    @staticmethod
    def table(device: str) -> str:
        return device.lower()

    def endpoint(self) -> str:
        """SQL query endpoint as seen by clients on the host (TimeSeries LinkedSegment `Endpoint`)."""
        return (f"{self.config['public_url'].rstrip('/')}/api/v3/query_sql"
                f"?db={self.database}&format={self.config.get('query_format', 'json')}")

    def linked_query(self, device: str, columns: list[str]) -> str:
        """TimeSeries LinkedSegment `Query`: the recorded variables of one device over the query window."""
        selected = ", ".join(quote_ident(c) for c in ["time", *columns])
        return (f"SELECT {selected} FROM {quote_ident(self.table(device))} "
                f"WHERE time >= now() - INTERVAL '{self.config['query_window']}' ORDER BY time")


TRANSIENT_STATUS = {502, 503, 504}  # InfluxDB reports SQL schema/planning errors as 500: not transient


class InfluxError(RuntimeError):
    """`transient` errors (server unreachable, gateway errors) are worth retrying; others (rejected lines,
    unknown table or column) are not."""

    def __init__(self, message: str, transient: bool):
        super().__init__(message)
        self.transient = transient


class InfluxClient:
    def __init__(self, base_url: str, database: str, timeout: float = 10.0,
                 client: httpx.Client | None = None):
        self.database = database
        self.http = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def write(self, lines: list[str]) -> None:
        try:
            response = self.http.post("/api/v3/write_lp", content="\n".join(lines).encode(),
                                      params={"db": self.database, "precision": "millisecond"})
        except httpx.HTTPError as exc:
            raise InfluxError(f"write: {exc}", transient=True) from exc
        if response.status_code >= 300:
            raise InfluxError(f"write: HTTP {response.status_code} {response.text[:300]}",
                              transient=response.status_code in TRANSIENT_STATUS)

    def query(self, sql: str) -> list[dict]:
        try:
            body = {"db": self.database, "q": sql, "format": "json"}
            response = self.http.post("/api/v3/query_sql", json=body)
        except httpx.HTTPError as exc:
            raise InfluxError(f"query: {exc}", transient=True) from exc
        if response.status_code >= 300:
            raise InfluxError(f"query: HTTP {response.status_code} {response.text[:300]}",
                              transient=response.status_code in TRANSIENT_STATUS)
        return response.json() if response.content else []
