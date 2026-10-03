"""ISA-18.2 alarm management without servers: master alarm database vs. the PLC alarm table, the alarm state
machine (ack, return to normal, shelving, suppression by design and by state), the UNS handling and the
API."""

from __future__ import annotations

import json
import re

import pytest

from alarms.api import router
from alarms.catalog import Catalog
from alarms.lifecycle import AlarmEngine
from alarms.service import AlarmService, parse_codes
from vf_common.mqtt import Message
from vf_common.uns import Uns

ROOT = "vf/plant01/final-assembly/line01"
EXECUTE, ABORTED = 6, 9


@pytest.fixture()
def engine():
    return AlarmEngine(Catalog.load())


def _states(engine):
    return {code: a.state for code, a in engine.alarms.items() if a.state != "NORM"}


def test_master_alarm_database_matches_the_plc_alarm_table():
    gd = (Catalog.load.__globals__["default_path"]().parents[1] / "godot" / "control" / "sorting_line" /
          "line_alarms.gd").read_text()
    plc = {int(code): text for code, text in re.findall(r'^\t(\d+): \["([^"]+)"', gd, re.MULTILINE)}
    catalog = Catalog.load()
    assert {c: d.text_en for c, d in catalog.alarms.items() if d.source == "PLC01"} == plc
    assert {d.source for d in catalog.alarms.values()} == {"PLC01", "MAINTENANCE"}
    ranks = [catalog.alarms[c].rank for c in plc]  # PLC table order = priority order
    assert ranks == sorted(ranks)
    assert all(d.text_de and d.remedy_en and d.remedy_de for d in catalog.alarms.values())


def test_activate_acknowledge_return_to_normal(engine):
    [t] = engine.process({101}, EXECUTE, 10.0)
    assert (t.event, t.state, t.priority, t.annunciated) == ("ACTIVATED", "UNACK", "High", True)
    assert engine.ack(101, "op1", 12.0).state == "ACKED"
    assert [t.event for t in engine.process(set(), EXECUTE, 20.0)] == ["CLEARED"]
    assert _states(engine) == {}
    engine.process({202}, EXECUTE, 30.0)
    engine.process(set(), EXECUTE, 31.0)
    assert _states(engine) == {202: "RTNUN"}  # returned without acknowledgement
    with pytest.raises(ValueError):
        engine.ack(101, "op1", 32.0)
    assert [t.state for t in engine.ack_all("op1", 33.0)] == ["NORM"]


def test_consequential_alarm_is_suppressed_by_design(engine):
    transitions = engine.process({100, 201}, ABORTED, 1.0)
    by_code = {t.code: t for t in transitions if t.event == "ACTIVATED"}
    assert by_code[100].annunciated and not by_code[201].annunciated
    assert _states(engine) == {100: "UNACK", 201: "DSUPR"}
    events = [(t.code, t.event) for t in engine.process({201}, ABORTED, 5.0)]
    assert (201, "UNSUPPRESSED") in events and (100, "CLEARED") in events
    assert _states(engine)[201] == "UNACK"  # still active after the E-stop: annunciated now
    engine.process(set(), ABORTED, 6.0)
    [t] = engine.process({401}, ABORTED, 7.0)  # infeed timeout meaningless while ABORTED (state-based)
    assert (t.event, t.state, t.annunciated) == ("ACTIVATED", "DSUPR", False)


def test_shelving_is_time_limited(engine):
    engine.process({302}, EXECUTE, 0.0)
    with pytest.raises(ValueError):
        engine.shelve(302, 10 * 3600, "op1", 1.0)  # longer than max_shelve_s
    assert engine.shelve(302, 60, "op1", 1.0, "sensor being cleaned").state == "SHLVD"
    assert [t.annunciated for t in engine.process(set(), EXECUTE, 2.0)] == [False]
    assert [t.annunciated for t in engine.process({302}, EXECUTE, 3.0)] == [False]
    assert engine.expire(30.0) == []
    [expired] = engine.expire(61.0)
    assert expired.event == "SHELVE_EXPIRED" and expired.state == "UNACK"


def test_unknown_codes_and_chattering(engine):
    for t in range(3):
        engine.process({999}, EXECUTE, float(t * 10))
        engine.process(set(), EXECUTE, float(t * 10 + 1))
    assert engine.alarms[999].definition.priority == "Medium"
    assert len(engine.alarms[999].activations) == 3
    assert parse_codes("100,201") == {100, 201} and parse_codes("") == set() and parse_codes(0) == set()


class _Db:
    def __init__(self):
        self.records, self.events = [], []

    def record(self, transition, alarm, session):
        self.records.append((transition.code, transition.event, session))

    def ensure_definition(self, definition):
        pass

    def journal_event(self, kind, topic, payload, device=None, name=None, session=None, seq=None,
                      source_time=None):
        self.events.append((kind, device, name, session))

    def execute(self, sql, params=None):
        return []


def engine_state(service, code):
    return service.engine.alarms[code].state


def _msg(topic, payload):
    return Message(f"{ROOT}/{topic}", json.dumps(payload).encode())


def test_uns_handling_and_journal():
    db = _Db()
    service = AlarmService(AlarmEngine(Catalog.load()), db, Uns.load())
    service.handle(_msg("session", {"id": "S-1", "ts": "2026-10-03T10:00:00Z"}))
    service.handle(_msg("plc01/alarm_code", {"v": 101}))  # fallback before the alarm word
    service.handle(_msg("plc01/active_alarms", {"v": "101,401"}))
    service.handle(_msg("plc01/alarm_code", {"v": 0}))  # ignored once the alarm word is known
    service.handle(_msg("plc01/packml_state", {"v": ABORTED}))
    service.handle(_msg("plc01/event/part_sorted", {"event": "part_sorted", "seq": 3, "session": "S-1"}))
    service.handle(_msg("plc01/cmd/packml_command", {"v": 9, "source": "hmi"}))
    assert db.records[:2] == [(101, "ACTIVATED", "S-1"), (401, "ACTIVATED", "S-1")]
    assert engine_state(service, 401) == "DSUPR"  # 101 active (consequence) / ABORTED (state)
    assert [e[0] for e in db.events] == ["session", "state", "event", "command"]
    assert db.events[2] == ("event", "PLC01", "part_sorted", "S-1")


def test_api_actions():
    service = AlarmService(AlarmEngine(Catalog.load()), _Db(), Uns.load())
    api = router(service)
    service.handle(_msg("plc01/active_alarms", {"v": "202"}))
    alarms = api.dispatch("GET", "/api/alarms").body
    assert [(a["code"], a["state"], a["priority"]) for a in alarms] == [(202, "UNACK", "High")]
    assert api.dispatch("POST", "/api/alarms/202/ack", b"{}").status == 400  # operator required
    ack = api.dispatch("POST", "/api/alarms/202/ack", b'{"operator": "hmi", "comment": "fault reset"}')
    assert ack.status == 200 and ack.body["state"] == "ACKED"
    assert api.dispatch("POST", "/api/alarms/202/ack", b'{"operator": "hmi"}').status == 409
    shelve = api.dispatch("POST", "/api/alarms/202/shelve", b'{"operator": "hmi", "durationS": 600}')
    assert shelve.body["state"] == "SHLVD"
    unshelve = api.dispatch("POST", "/api/alarms/202/unshelve", b'{"operator": "hmi"}')
    assert unshelve.body["event"] == "UNSHELVED"
    assert api.dispatch("GET", "/api/alarms/7").status == 404
    assert len(api.dispatch("GET", "/api/definitions").body) == 8  # 7 PLC alarms + 1 maintenance


def test_maintenance_alarm_word_is_merged_with_the_plc_alarms():
    """Advisory alarms of the maintenance service (source MAINTENANCE, ADR-0029) live next to the PLC alarms:
    one alarm word does not clear the other."""
    db = _Db()
    service = AlarmService(AlarmEngine(Catalog.load()), db, Uns.load())
    service.handle(_msg("plc01/active_alarms", {"v": "202"}))
    service.handle(_msg("maintenance/active_alarms", {"v": "901"}))
    assert (engine_state(service, 202), engine_state(service, 901)) == ("UNACK", "UNACK")
    definition = service.engine.alarms[901].definition
    assert (definition.priority, definition.alarm_class, definition.source) == ("Low", "Diagnostic",
                                                                                "MAINTENANCE")
    service.handle(_msg("plc01/active_alarms", {"v": ""}))
    assert engine_state(service, 901) == "UNACK" and engine_state(service, 202) == "RTNUN"
    service.handle(_msg("maintenance/active_alarms", {"v": ""}))
    assert engine_state(service, 901) == "RTNUN"
    assert service.active == set()
