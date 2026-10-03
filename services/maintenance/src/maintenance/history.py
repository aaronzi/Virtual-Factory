"""Measured history of a component from the historian (InfluxDB 3, SQL; ADR-0019): one row per operating
cycle of the device table (the indicator, the cycle counter and the symptoms change in the same simulation
tick, so the historian merges them into one row). Newest `max_points` rows of the session, oldest first."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from vf_common.historian import HistorianConfig, InfluxClient, quote_ident

from .config import Component
from .prognosis import Sample


@dataclass(frozen=True)
class Readings:
    samples: list[Sample]
    latest: dict = field(default_factory=dict)  # newest value of every component variable


def parse_time(text: str) -> float:
    parsed = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def query(component: Component, session: str | None, max_points: int) -> str:
    columns = ", ".join(quote_ident(c) for c in ["time", *component.variables])
    where = [f"{quote_ident(component.cycles)} IS NOT NULL",
             f"{quote_ident(component.indicator)} IS NOT NULL"]
    if session:
        where.append(f"session = {_literal(session)}")
    return (f"SELECT {columns} FROM {quote_ident(HistorianConfig.table(component.device))} "
            f"WHERE {' AND '.join(where)} ORDER BY time DESC LIMIT {int(max_points)}")


class History:
    def __init__(self, influx: InfluxClient, max_points: int = 200):
        self.influx, self.max_points = influx, max_points

    def readings(self, component: Component, session: str | None) -> Readings:
        rows = list(reversed(self.influx.query(query(component, session, self.max_points))))
        samples = [Sample(parse_time(r["time"]), int(r[component.cycles]), float(r[component.indicator]))
                   for r in rows]
        latest: dict = {}
        for row in rows:  # forward fill: unchanged outputs are not repeated in later rows
            latest.update({k: v for k, v in row.items() if v is not None})
        return Readings(samples, latest)
