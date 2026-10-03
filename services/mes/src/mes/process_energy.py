"""Energy of one part from the historian (InfluxDB 3, ADR-0019), method in docs/interfaces/aas-model.md §6a:

- assembly cell (one part at a time): the cell's whole energy of the part's cycle, from the previous release
  to this release (idle and blocked time included), and the compressed air consumed in that cycle;
- downstream devices (conveyor, light barriers, inspection, robot, stack light): their power between release
  and sort, shared equally among the parts in process at each instant (released - sorted, from the counters
  AC01.release_count and PLC01.sorted_count)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from vf_common.historian import HistorianConfig, InfluxClient, InfluxError, quote_ident

from .allocation import Series, counter_difference, difference, integrate, run_start

J_PER_KWH = 3.6e6


@dataclass(frozen=True)
class PartEnergy:
    cell_kwh: float      # assembly cell incl. the compressed-air equivalent contained in its power
    air_nl: float        # compressed air of the cell cycle
    line_kwh: float      # downstream devices, residence-time share
    cycle_s: float
    residence_s: float


class ProcessEnergy:
    def __init__(self, influx: InfluxClient, downstream: list[str], cell: str = "ac01",
                 controller: str = "plc01", max_cycle_s: float = 1800.0):
        self.influx, self.downstream, self.cell, self.controller = influx, downstream, cell, controller
        self.max_cycle_s = max_cycle_s

    def for_part(self, v: dict, wait_s: float = 3.0) -> PartEnergy:
        session, released, sorted_at = str(v["session"]), parse(v["releasedAt"]), parse(v["sortedAt"])
        self.wait_for(session, sorted_at, wait_s)
        floor = released - self.max_cycle_s
        start = run_start(self.series(self.cell, "release_count", session, floor, released), released, floor)
        cell_j = integrate(self.series(self.cell, "power", session, start, released), start, released)
        air = difference(self.series(self.cell, "air_consumption", session, start, released), start, released)
        in_process = counter_difference(self.series(self.cell, "release_count", session, released, sorted_at),
                                        self.series(self.controller, "sorted_count", session, released,
                                                    sorted_at))
        line_j = sum(self._device_energy(table, session, released, sorted_at, in_process)
                     for table in self.downstream)
        return PartEnergy(cell_j / J_PER_KWH, air, line_j / J_PER_KWH, released - start, sorted_at - released)

    def _device_energy(self, table: str, session: str, t0: float, t1: float, in_process: Series) -> float:
        try:
            return integrate(self.series(table, "power", session, t0, t1), t0, t1, in_process)
        except InfluxError as exc:
            if exc.transient:
                raise
            return 0.0  # device without recorded power in this session

    def series(self, table: str, column: str, session: str, t0: float, t1: float) -> Series:
        """Samples of one column in [t0, t1] plus the last sample before t0 (the value held at t0)."""
        col, tab, sess = quote_ident(column), quote_ident(table), _literal(session)
        base = f"SELECT time, {col} AS v FROM {tab} WHERE session = {sess} AND {col} IS NOT NULL"
        sql = (f"({base} AND time < {_ts(t0)} ORDER BY time DESC LIMIT 1) UNION ALL "
               f"({base} AND time >= {_ts(t0)} AND time <= {_ts(t1)})")
        rows = self.influx.query(sql)
        return sorted((parse(r["time"]), float(r["v"])) for r in rows if r.get("v") is not None)

    def wait_for(self, session: str, t: float, timeout: float) -> bool:
        """Waits until the historian has stored the controller's sort counter up to t (batching delay)."""
        deadline = time.monotonic() + timeout
        while True:
            rows = self.influx.query(f"SELECT max(time) AS t FROM {quote_ident(self.controller)} "
                                     f"WHERE session = {_literal(session)} AND sorted_count IS NOT NULL")
            latest = rows[0].get("t") if rows else None
            if latest and parse(latest) >= t - 0.001:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)


def power_tables(specs: list[dict], cell: str = "ac01") -> list[str]:
    """Historian tables of the devices with a live power output (asset data `device.energy.power`), without
    the assembly cell."""
    tables = [HistorianConfig.table(s["device"].get("instance", s["tag"])) for s in specs
              if (s.get("device") or {}).get("energy", {}).get("power")]
    return sorted(t for t in tables if t != cell)


def parse(text: str) -> float:
    """ISO 8601 (with Z, an offset or naive UTC as returned by InfluxDB) -> Unix seconds."""
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _ts(t: float) -> str:
    stamp = datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")
    return "'" + stamp.replace("+00:00", "Z") + "'"


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"
