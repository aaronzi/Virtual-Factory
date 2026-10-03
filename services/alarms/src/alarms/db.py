"""TimescaleDB access of the alarms service (psycopg 3, one connection guarded by a lock; the rates are low:
a few alarm transitions and UNS events per second at most). Schema: schema.sql."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .catalog import AlarmDefinition, Catalog
from .lifecycle import Alarm, Transition

log = logging.getLogger("alarms.db")
SCHEMA = Path(__file__).with_name("schema.sql")


def ts(t: float | None) -> datetime | None:
    return None if t is None else datetime.fromtimestamp(t, timezone.utc)


def epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def _excluded(*columns: str) -> str:
    """ ' col = EXCLUDED.col, ...' of an upsert."""
    return " " + ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)


class Database:
    def __init__(self, url: str):
        self.url = url
        self.conn: psycopg.Connection | None = None
        self.lock = threading.RLock()

    def connect(self, retry_s: float = 3.0) -> None:
        while True:
            try:
                self.conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
                return
            except psycopg.OperationalError as exc:
                log.info("waiting for TimescaleDB: %s", str(exc).strip().splitlines()[0])
                time.sleep(retry_s)

    def execute(self, sql: str, params: Any = None) -> list[dict]:
        with self.lock:
            for attempt in (1, 2):
                try:
                    cur = self.conn.execute(sql, params)
                    return cur.fetchall() if cur.description else []
                except psycopg.OperationalError:
                    if attempt == 2:
                        raise
                    log.warning("database connection lost, reconnecting")
                    self.connect()
        return []

    def init_schema(self, catalog: Catalog) -> None:
        self.execute(SCHEMA.read_text(encoding="utf-8"))
        for definition in catalog.alarms.values():
            self.ensure_definition(definition)

    def ensure_definition(self, d: AlarmDefinition) -> None:
        self.execute(
            "INSERT INTO alarm_definition (code, source, text_en, text_de, priority, priority_rank,"
            " alarm_class, reaction, response_s, remedy_en, remedy_de, suppressed_by, suppress_in_states)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (code) DO UPDATE SET"
            + _excluded("source", "text_en", "text_de", "priority", "priority_rank", "alarm_class",
                        "reaction", "response_s", "remedy_en", "remedy_de", "suppressed_by",
                        "suppress_in_states"),
            (d.code, d.source, d.text_en, d.text_de, d.priority, d.rank, d.alarm_class, d.reaction,
             d.response_s, d.remedy_en, d.remedy_de, list(d.suppressed_by), list(d.suppress_in_states)))

    def record(self, transition: Transition, alarm: Alarm, session: str | None) -> None:
        """Journal entry, occurrence and current state of one transition (one database round trip each)."""
        with self.lock:
            occurrence = self._occurrence(transition, alarm, session)
            self.execute("INSERT INTO alarm_journal (time, code, event, state, priority, annunciated,"
                         " operator, comment, session, occurrence_id)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (ts(transition.time), transition.code, transition.event, transition.state,
                          transition.priority, transition.annunciated, transition.operator or None,
                          transition.comment or None, session, occurrence))
            self._state(alarm, occurrence, session, transition.time)

    def _occurrence(self, t: Transition, alarm: Alarm, session: str | None) -> int | None:
        if t.event == "ACTIVATED":
            rows = self.execute("INSERT INTO alarm_occurrence (code, session, priority, activated_at,"
                                " annunciated) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                                (t.code, session, t.priority, ts(t.time), t.annunciated))
            return rows[0]["id"]
        current = self.execute("SELECT occurrence_id FROM alarm_state WHERE code = %s", (t.code,))
        occurrence = current[0]["occurrence_id"] if current else None
        if occurrence and t.event == "ACKNOWLEDGED":
            self.execute("UPDATE alarm_occurrence SET acked_at = %s, acked_by = %s"
                         " WHERE id = %s AND acked_at IS NULL", (ts(t.time), t.operator, occurrence))
        elif occurrence and t.event == "CLEARED":
            self.execute("UPDATE alarm_occurrence SET cleared_at = %s WHERE id = %s",
                         (ts(t.time), occurrence))
        elif occurrence and t.event == "UNSUPPRESSED" and alarm.active and not alarm.hidden:
            self.execute("UPDATE alarm_occurrence SET annunciated = TRUE WHERE id = %s", (occurrence,))
        return occurrence

    def _state(self, a: Alarm, occurrence: int | None, session: str | None, now: float) -> None:
        self.execute(
            "INSERT INTO alarm_state (code, state, active, acked, suppressed, shelved_until, shelved_by,"
            " activated_at, acked_at, acked_by, cleared_at, occurrence_id, session, comment, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            + _excluded("state", "active", "acked", "suppressed", "shelved_until", "shelved_by",
                        "activated_at", "acked_at", "acked_by", "cleared_at", "occurrence_id", "session",
                        "comment", "updated_at"),
            (a.definition.code, a.state, a.active, a.acked, a.suppressed, ts(a.shelved_until),
             a.shelved_by or None, ts(a.activated_at), ts(a.acked_at), a.acked_by or None, ts(a.cleared_at),
             occurrence, session, a.comment or None, ts(now)))

    def load_states(self) -> list[dict]:
        return self.execute("SELECT * FROM alarm_state")

    def journal_event(self, kind: str, topic: str, payload: Any, device: str | None = None,
                      name: str | None = None, session: str | None = None, seq: int | None = None,
                      source_time: str | None = None) -> None:
        source = None
        if source_time:
            try:
                source = datetime.fromisoformat(str(source_time).replace("Z", "+00:00"))
            except ValueError:
                source = None
        self.execute("INSERT INTO event_journal (time, kind, device, name, topic, session, seq, source_time,"
                     " payload) VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s)",
                     (kind, device, name, topic, session, seq, source, json.dumps(payload)))
