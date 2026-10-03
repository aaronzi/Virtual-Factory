"""ISA-18.2 alarm state machine (pure, no I/O). States of one alarm:

    NORM   normal: process condition inactive, acknowledged                       (ISA-18.2 state A)
    UNACK  active, unacknowledged - annunciated                                   (B)
    ACKED  active, acknowledged                                                   (C)
    RTNUN  returned to normal, unacknowledged                                     (D)
    SHLVD  shelved by the operator (for a limited time)                           (E)
    DSUPR  active but suppressed by design: consequence of another active alarm or
           a plant state in which the alarm is meaningless (master alarm database) (F)

Out-of-service (G) is not used. Shelved and suppressed alarms keep tracking the process condition (journal);
they are not annunciated and need no acknowledgement for what happened while hidden. When they return, an
active alarm is annunciated again (UNACK), an inactive one is NORM. Transitions carry the event name used in
the journal: ACTIVATED, CLEARED (return to normal), ACKNOWLEDGED, SHELVED, UNSHELVED, SHELVE_EXPIRED,
SUPPRESSED, UNSUPPRESSED."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .catalog import AlarmDefinition, Catalog


@dataclass
class Alarm:
    definition: AlarmDefinition
    active: bool = False
    acked: bool = True
    shelved_until: float | None = None
    suppressed: bool = False
    activated_at: float | None = None
    acked_at: float | None = None
    cleared_at: float | None = None
    acked_by: str = ""
    shelved_by: str = ""
    comment: str = ""
    activations: list[float] = field(default_factory=list)  # recent activation times (chattering)

    @property
    def hidden(self) -> bool:
        return self.shelved_until is not None or self.suppressed

    @property
    def state(self) -> str:
        if self.shelved_until is not None:
            return "SHLVD"
        if self.suppressed and self.active:
            return "DSUPR"
        if self.active:
            return "ACKED" if self.acked else "UNACK"
        return "NORM" if self.acked else "RTNUN"


@dataclass(frozen=True)
class Transition:
    time: float
    code: int
    event: str
    state: str
    priority: str
    annunciated: bool = True
    operator: str = ""
    comment: str = ""


class AlarmEngine:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.alarms: dict[int, Alarm] = {code: Alarm(d) for code, d in catalog.alarms.items()}
        self.packml_state: int | None = None
        self.lock = threading.RLock()

    def _alarm(self, code: int) -> Alarm:
        if code not in self.alarms:
            self.alarms[code] = Alarm(self.catalog.get(code))
        return self.alarms[code]

    def _emit(self, alarm: Alarm, event: str, now: float, operator: str = "",
              comment: str = "") -> Transition:
        return Transition(now, alarm.definition.code, event, alarm.state, alarm.definition.priority,
                          not alarm.hidden, operator, comment)

    def process(self, active: set[int], packml_state: int | None, now: float) -> list[Transition]:
        """Applies the active alarm codes of the PLC (and its PackML state) at time `now`."""
        with self.lock:
            if packml_state is not None:
                self.packml_state = packml_state
            for code in active:
                self._alarm(code)
            out: list[Transition] = []
            for alarm in sorted(self.alarms.values(), key=lambda a: (a.definition.rank, a.definition.code)):
                out += self._suppression(alarm, active, now)
                out += self._condition(alarm, alarm.definition.code in active, now)
            return out

    def _suppression(self, alarm: Alarm, active: set[int], now: float) -> list[Transition]:
        d = alarm.definition
        wanted = any(code in active for code in d.suppressed_by) or self.packml_state in d.suppress_in_states
        if wanted == alarm.suppressed:
            return []
        alarm.suppressed = wanted
        if not alarm.active:
            return []  # journaled only for an active alarm (an inactive one is NORM either way)
        if not wanted and alarm.shelved_until is None:
            alarm.acked = False  # annunciated again
        return [self._emit(alarm, "SUPPRESSED" if wanted else "UNSUPPRESSED", now)]

    def _condition(self, alarm: Alarm, on: bool, now: float) -> list[Transition]:
        if on == alarm.active:
            return []
        alarm.active = on
        if on:
            alarm.acked, alarm.activated_at, alarm.acked_by = False, now, ""
            window = self.catalog.chattering.get("window_s", 60)
            alarm.activations = [t for t in alarm.activations if now - t <= window] + [now]
            return [self._emit(alarm, "ACTIVATED", now)]
        alarm.cleared_at = now
        if alarm.hidden:
            alarm.acked = True
        return [self._emit(alarm, "CLEARED", now)]

    def ack(self, code: int, operator: str, now: float, comment: str = "") -> Transition:
        with self.lock:
            alarm = self.alarms.get(code)
            if alarm is None or alarm.state not in ("UNACK", "RTNUN"):
                state = alarm.state if alarm else "unknown"
                raise ValueError(f"alarm {code} is not unacknowledged ({state})")
            alarm.acked, alarm.acked_at, alarm.acked_by = True, now, operator
            return self._emit(alarm, "ACKNOWLEDGED", now, operator, comment)

    def ack_all(self, operator: str, now: float) -> list[Transition]:
        with self.lock:
            codes = [c for c, a in self.alarms.items() if a.state in ("UNACK", "RTNUN")]
            return [self.ack(code, operator, now) for code in codes]

    def shelve(self, code: int, duration_s: float, operator: str, now: float,
               comment: str = "") -> Transition:
        with self.lock:
            alarm = self.alarms.get(code)
            if alarm is None:
                raise ValueError(f"unknown alarm {code}")
            if not 0 < duration_s <= self.catalog.max_shelve_s:
                raise ValueError(f"shelving duration must be 1..{self.catalog.max_shelve_s} s")
            alarm.shelved_until, alarm.shelved_by, alarm.comment = now + duration_s, operator, comment
            return self._emit(alarm, "SHELVED", now, operator, comment)

    def unshelve(self, code: int, operator: str, now: float, event: str = "UNSHELVED") -> Transition:
        with self.lock:
            alarm = self.alarms.get(code)
            if alarm is None or alarm.shelved_until is None:
                raise ValueError(f"alarm {code} is not shelved")
            alarm.shelved_until, alarm.shelved_by = None, ""
            alarm.acked = not (alarm.active and not alarm.suppressed)
            return self._emit(alarm, event, now, operator)

    def expire(self, now: float) -> list[Transition]:
        """Ends shelving whose time is up (ISA-18.2: shelving is always time limited)."""
        with self.lock:
            due = [c for c, a in self.alarms.items()
                   if a.shelved_until is not None and a.shelved_until <= now]
            return [self.unshelve(code, "system", now, "SHELVE_EXPIRED") for code in due]
