"""ISO 22400 KPI elements of LINE01 (IDTA 02066 ProcessVariablesForManufacturingKPICalculation): times per
PackML state accumulated from the controller's packml_state telemetry (simulation time stamps) and the part
counters."""

from __future__ import annotations

from datetime import datetime

from vf_common import ids
from vf_common.basyx import BasyxClient

EXECUTE, SUSPENDED, HELD = 6, 5, 11
DOWN = {2, 7, 8, 9, 10}  # STOPPED, STOPPING, ABORTING, ABORTED, HOLDING
COUNTERS = {"parts_total": "InspectedPart", "parts_ok": "GoodPart"}


class KpiTracker:
    def __init__(self, line: str = "LINE01"):
        self.sm_id = ids.submodel_id(line, "ProcessVariablesForManufacturingKPICalculation", "1")
        self.reset()

    def reset(self) -> None:
        self.seconds = {"execute": 0.0, "suspended": 0.0, "held": 0.0, "down": 0.0}
        self.counters = {"parts_total": 0, "parts_ok": 0, "parts_nok": 0}
        self._state: int | None = None
        self._since: datetime | None = None

    def on_state(self, state: int, ts: str) -> None:
        t = _parse(ts)
        self._accumulate(t)
        self._state, self._since = state, t

    def on_counter(self, name: str, value: int) -> None:
        if name in self.counters:
            self.counters[name] = int(value)

    def values(self, now_ts: str | None = None) -> dict[str, str]:
        if now_ts:
            self._accumulate(_parse(now_ts))
        s = self.seconds
        busy = s["execute"] + s["suspended"] + s["held"]
        return {"ActualProductionTime": _duration(s["execute"]), "ActualUnitBusyTime": _duration(busy),
                "ActualUnitDelayTime": _duration(s["suspended"]),
                "ActualUnitDownTime": _duration(s["held"] + s["down"]),
                "InspectedPart": str(self.counters["parts_total"]),
                "GoodPart": str(self.counters["parts_ok"]),
                "ProducedQuantity": str(self.counters["parts_total"]),
                "ScrapQuantity": str(self.counters["parts_nok"])}

    def write(self, aas: BasyxClient, now_ts: str | None = None) -> None:
        for element, value in self.values(now_ts).items():
            aas.set_value(self.sm_id, f"{element}.currentValue", value)

    def _accumulate(self, t: datetime) -> None:
        if self._state is None or self._since is None or t <= self._since:
            return
        dt = (t - self._since).total_seconds()
        key = ("execute" if self._state == EXECUTE else "suspended" if self._state == SUSPENDED
               else "held" if self._state == HELD else "down" if self._state in DOWN else None)
        if key:
            self.seconds[key] += dt
        self._since = t


def _duration(seconds: float) -> str:
    """xs:duration, e.g. PT1H2M3S."""
    total = int(round(seconds))
    h, rest = divmod(total, 3600)
    m, sec = divmod(rest, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + f"{sec}S"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
