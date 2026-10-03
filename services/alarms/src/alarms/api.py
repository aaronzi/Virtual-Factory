"""REST API of the alarms service (port 8099):

    GET  /health
    GET  /api/alarms[?all=true]                 current alarms (not NORM; all=true: every known alarm)
    GET  /api/alarms/{code}
    POST /api/alarms/{code}/ack                 {"operator", "comment"?}
    POST /api/alarms/ack                        {"operator"} - acknowledge all unacknowledged alarms
    POST /api/alarms/{code}/shelve              {"durationS", "operator", "comment"?}  (max 8 h)
    POST /api/alarms/{code}/unshelve            {"operator"}
    GET  /api/journal[?since&until&code&event&limit]    alarm transitions (alarm_journal)
    GET  /api/events[?since&until&kind&name&device&limit]  UNS event journal (event_journal)
    GET  /api/kpis[?window=<minutes>]           alarm system performance (ISA-18.2 / EEMUA 191)
    GET  /api/definitions                       master alarm database
"""

from __future__ import annotations

from vf_common.http_api import ApiError, Request, Router

from . import queries
from .lifecycle import Transition
from .service import AlarmService


def router(service: AlarmService) -> Router:
    engine, db = service.engine, service.db
    r = Router()
    r.add("GET", "/health", lambda q: {"status": "ok", "session": service.session,
                                       "active": sorted(service.active), "alarmWord": service.word_seen})
    r.add("GET", "/api/alarms", lambda q: queries.current(engine, q.params.get("all") in ("1", "true")))
    r.add("GET", r"/api/alarms/(?P<code>\d+)", lambda q: _one(service, int(q.match["code"])))
    r.add("POST", "/api/alarms/ack", lambda q: [_t(t) for t in service.ack_all(_operator(q))])
    r.add("POST", r"/api/alarms/(?P<code>\d+)/ack", lambda q: _action(
        lambda: service.ack(int(q.match["code"]), _operator(q), (q.body or {}).get("comment", ""))))
    r.add("POST", r"/api/alarms/(?P<code>\d+)/shelve", lambda q: _action(
        lambda: service.shelve(int(q.match["code"]), float((q.body or {})["durationS"]), _operator(q),
                               (q.body or {}).get("comment", ""))))
    r.add("POST", r"/api/alarms/(?P<code>\d+)/unshelve", lambda q: _action(
        lambda: service.unshelve(int(q.match["code"]), _operator(q))))
    r.add("GET", "/api/journal", lambda q: queries.journal(db, q.params))
    r.add("GET", "/api/events", lambda q: queries.events(db, q.params))
    r.add("GET", "/api/kpis", lambda q: queries.kpis(db, engine, int(q.params.get("window", 60))))
    r.add("GET", "/api/definitions", lambda q: [d.to_dict() for d in engine.catalog.alarms.values()])
    return r


def _one(service: AlarmService, code: int) -> dict:
    alarm = service.engine.alarms.get(code)
    if alarm is None:
        raise ApiError(404, f"unknown alarm {code}")
    return queries.alarm_view(alarm)


def _operator(q: Request) -> str:
    operator = str((q.body or {}).get("operator") or "").strip()
    if not operator:
        raise ApiError(400, "operator is required (who acknowledges / shelves)")
    return operator[:64]


def _action(call) -> dict:
    try:
        return _t(call())
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


def _t(t: Transition) -> dict:
    return {"code": t.code, "event": t.event, "state": t.state, "time": queries.iso(t.time),
            "operator": t.operator or None, "comment": t.comment or None}
