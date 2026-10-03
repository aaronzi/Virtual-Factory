"""Minimal status page of the ERP simulator (static HTML + fetch calls to the REST API)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def status_page() -> str:
    return (Path(__file__).parent / "status.html").read_text(encoding="utf-8")
