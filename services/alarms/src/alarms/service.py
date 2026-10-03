"""Alarm server core: UNS messages -> ISA-18.2 engine -> TimescaleDB, and the operator actions of the API.

Inputs (topics from the UNS registry godot/config/uns.json):
    {root}/plc01/active_alarms   all active PLC alarms in priority order ("100,201"; PLC alarm word)
    {root}/plc01/alarm_code      fallback while active_alarms has not been received (highest alarm only)
    {root}/plc01/packml_state    state-based suppression; state changes are journaled
    {root}/session, /status      session birth / gateway status (journal)
    {root}/+/event/+             every UNS event (journal)
    {root}/+/cmd/+, /cmd-resp/+  commands and their acknowledgements (journal)
    {root}/maintenance/active_alarms  advisory alarm word of the maintenance service (source MAINTENANCE,
                                 ADR-0029); merged with the PLC alarm word
"""

from __future__ import annotations

import logging
import threading
import time

from vf_common.mqtt import Message
from vf_common.uns import Uns, telemetry_value

from .db import Database, epoch
from .lifecycle import AlarmEngine, Transition

log = logging.getLogger("alarms.service")
PLC = "PLC01"


def parse_codes(value) -> set[int]:
    text = "" if value is None else str(value)
    return {int(c) for c in text.replace(";", ",").split(",") if c.strip().lstrip("-").isdigit() and int(c)}


class AlarmService:
    def __init__(self, engine: AlarmEngine, db: Database, uns: Uns):
        self.engine, self.db, self.uns = engine, db, uns
        self.session: str | None = None
        self.active: set[int] = set()
        self.word_seen = False  # active_alarms received (else the alarm_code fallback is used)
        self.topics = {uns.telemetry(PLC, "active_alarms"): "word", uns.telemetry(PLC, "alarm_code"): "code",
                       uns.telemetry(PLC, "packml_state"): "state"}
        if uns.maintenance_alarm_topic:
            self.topics[uns.maintenance_alarm_topic] = "maintenance"
        self.plc_active: set[int] = set()
        self.maintenance_active: set[int] = set()
        self._lock = threading.Lock()

    def subscriptions(self) -> list[str]:
        cmd = self.uns.command("+", "+")
        return [*self.topics, self.uns.session_topic, self.uns.status_topic, self.uns.all_events(), cmd,
                self.uns.ack("+", "+")]

    def restore(self) -> None:
        """Current alarm states from the database (service restart keeps acknowledgements and shelving)."""
        with self.engine.lock:
            for row in self.db.load_states():
                alarm = self.engine._alarm(row["code"])
                alarm.active, alarm.acked, alarm.suppressed = row["active"], row["acked"], row["suppressed"]
                alarm.shelved_until = epoch(row["shelved_until"])
                alarm.activated_at, alarm.acked_at = epoch(row["activated_at"]), epoch(row["acked_at"])
                alarm.cleared_at, alarm.acked_by = epoch(row["cleared_at"]), row["acked_by"] or ""
                alarm.shelved_by, alarm.comment = row["shelved_by"] or "", row["comment"] or ""
                if alarm.active:
                    self.active.add(row["code"])
                    source = self.maintenance_active if alarm.definition.source == "MAINTENANCE" \
                        else self.plc_active
                    source.add(row["code"])
                self.session = row["session"] or self.session

    def handle(self, msg: Message, now: float | None = None) -> list[Transition]:
        now = time.time() if now is None else now
        kind = self.topics.get(msg.topic)
        if kind:
            return self._telemetry(kind, telemetry_value(msg.payload), msg, now)
        data = msg.json() if isinstance(msg.json(), dict) else {}
        if msg.topic == self.uns.session_topic:
            self.session = data.get("id") or self.session
            self._journal("session", msg, data, name="session")
        elif msg.topic == self.uns.status_topic:
            self._journal("status", msg, data, name=str(data.get("v")))
        else:
            parts = msg.topic[len(self.uns.root) + 1:].split("/")
            if len(parts) == 3 and parts[1] in ("event", "cmd", "cmd-resp"):
                kind = {"event": "event", "cmd": "command", "cmd-resp": "ack"}[parts[1]]
                self._journal(kind, msg, data, device=parts[0].upper(), name=parts[2])
        return []

    def _telemetry(self, kind: str, value, msg: Message, now: float) -> list[Transition]:
        if kind == "state":
            if value is None or int(value) == self.engine.packml_state:
                return []
            self._journal("state", msg, msg.json(), device=PLC, name="packml_state")
            return self._apply(self.active, int(value), now)
        if kind == "maintenance":
            self.maintenance_active = parse_codes(value)
            return self._apply(self.plc_active | self.maintenance_active, None, now)
        if kind == "word":
            self.word_seen = True
        elif self.word_seen:
            return []  # alarm_code only while the PLC does not report its alarm word
        self.plc_active = parse_codes(value)
        return self._apply(self.plc_active | self.maintenance_active, None, now)

    def _apply(self, active: set[int], state: int | None, now: float) -> list[Transition]:
        with self._lock:
            self.active = set(active)
            transitions = self.engine.process(self.active, state, now)
            self._record(transitions)
        return transitions

    def _record(self, transitions: list[Transition]) -> None:
        for t in transitions:
            alarm = self.engine.alarms[t.code]
            if t.code not in self.engine.catalog.alarms:
                self.db.ensure_definition(alarm.definition)
            self.db.record(t, alarm, self.session)
            log.info("alarm %d %s -> %s%s", t.code, t.event, t.state,
                     f" by {t.operator}" if t.operator else "")

    def _journal(self, kind: str, msg: Message, data, device: str | None = None,
                 name: str | None = None) -> None:
        payload = data if isinstance(data, dict) else {"raw": msg.payload.decode(errors="replace")}
        self.db.journal_event(kind, msg.topic, payload, device or payload.get("device"), name,
                              payload.get("session") or self.session, payload.get("seq"), payload.get("ts"))

    # -- operator actions (API) -----------------------------------------------------------------------

    def ack(self, code: int, operator: str, comment: str = "") -> Transition:
        with self._lock:
            transition = self.engine.ack(code, operator, time.time(), comment)
            self._record([transition])
        return transition

    def ack_all(self, operator: str) -> list[Transition]:
        with self._lock:
            transitions = self.engine.ack_all(operator, time.time())
            self._record(transitions)
        return transitions

    def shelve(self, code: int, duration_s: float, operator: str, comment: str = "") -> Transition:
        with self._lock:
            transition = self.engine.shelve(code, duration_s, operator, time.time(), comment)
            self._record([transition])
        return transition

    def unshelve(self, code: int, operator: str) -> Transition:
        with self._lock:
            transition = self.engine.unshelve(code, operator, time.time())
            self._record([transition])
        return transition

    def expire(self, now: float | None = None) -> None:
        with self._lock:
            self._record(self.engine.expire(time.time() if now is None else now))
