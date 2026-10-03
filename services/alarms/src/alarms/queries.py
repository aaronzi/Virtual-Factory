"""Read side of the alarms API: current alarms (from the engine), journal and event queries, and the alarm
system performance KPIs after ISA-18.2 / EEMUA 191 (from the database):

    rate            annunciated alarms per 10 minutes (average and peak over the window; EEMUA 191:
                    <= 1 per 10 min "very likely acceptable", > 10 per 10 min = alarm flood)
    flood           share of 10-minute periods with more than `flood.per_10min` alarms
    standing        alarms active now; stale = active longer than `stale_after_s`
    bad actors      top 10 alarms by number of activations and their share of all activations
    chattering      alarms activated >= chattering.count times within chattering.window_s
    priorities      distribution of the activations per priority (target roughly 80/15/5 % low/medium/high)
    response        mean time to acknowledge and to return to normal
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .db import Database, ts
from .lifecycle import Alarm, AlarmEngine


def iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


def alarm_view(a: Alarm) -> dict:
    d = a.definition
    return {"code": d.code, "source": d.source, "state": a.state, "priority": d.priority,
            "priorityRank": d.rank, "class": d.alarm_class, "text": {"en": d.text_en, "de": d.text_de},
            "remedy": {"en": d.remedy_en, "de": d.remedy_de}, "active": a.active, "acknowledged": a.acked,
            "suppressed": a.suppressed, "shelvedUntil": iso(a.shelved_until),
            "shelvedBy": a.shelved_by or None,
            "activatedAt": iso(a.activated_at), "acknowledgedAt": iso(a.acked_at),
            "acknowledgedBy": a.acked_by or None, "clearedAt": iso(a.cleared_at),
            "comment": a.comment or None}


def current(engine: AlarmEngine, include_normal: bool = False) -> list[dict]:
    with engine.lock:
        alarms = [a for a in engine.alarms.values() if include_normal or a.state != "NORM"]
        alarms.sort(key=lambda a: (a.definition.rank, -(a.activated_at or 0)))
        return [alarm_view(a) for a in alarms]


def journal(db: Database, params: dict) -> list[dict]:
    sql, args = "SELECT * FROM alarm_journal WHERE time >= %s AND time <= %s", [*_range(params)]
    if params.get("code"):
        sql, args = sql + " AND code = %s", [*args, int(params["code"])]
    if params.get("event"):
        sql, args = sql + " AND event = %s", [*args, params["event"].upper()]
    return db.execute(sql + " ORDER BY time DESC LIMIT %s", [*args, _limit(params)])


def events(db: Database, params: dict) -> list[dict]:
    sql, args = "SELECT * FROM event_journal WHERE time >= %s AND time <= %s", [*_range(params)]
    for key in ("kind", "name", "device"):
        if params.get(key):
            sql, args = sql + f" AND {key} = %s", [*args, params[key]]
    return db.execute(sql + " ORDER BY time DESC LIMIT %s", [*args, _limit(params)])


def kpis(db: Database, engine: AlarmEngine, window_min: int = 60) -> dict:
    catalog, since = engine.catalog, ts(time.time() - window_min * 60)
    buckets = [r["n"] for r in db.execute(
        "SELECT time_bucket('10 minutes', activated_at) AS b, count(*) AS n FROM alarm_occurrence"
        " WHERE annunciated AND activated_at >= %s GROUP BY 1", (since,))]
    periods = max(1, window_min // 10)
    total = sum(buckets)
    actors = db.execute(
        "SELECT o.code, d.text_en AS text, d.priority, count(*) AS activations FROM alarm_occurrence o"
        " JOIN alarm_definition d USING (code) WHERE activated_at >= %s GROUP BY 1, 2, 3"
        " ORDER BY activations DESC, o.code LIMIT 10", (since,))
    all_activations = sum(a["activations"] for a in actors) or 1
    chatter = db.execute(
        "SELECT code, max(n) AS max_in_window FROM (SELECT code, count(*) OVER (PARTITION BY code ORDER BY"
        " activated_at RANGE BETWEEN %s * INTERVAL '1 second' PRECEDING AND CURRENT ROW) AS n"
        " FROM alarm_occurrence WHERE activated_at >= %s) x GROUP BY code HAVING max(n) >= %s",
        (catalog.chattering.get("window_s", 60), since, catalog.chattering.get("count", 3)))
    priorities = db.execute("SELECT priority, count(*) AS n FROM alarm_occurrence WHERE activated_at >= %s"
                            " GROUP BY 1", (since,))
    response = db.execute(
        "SELECT avg(extract(epoch FROM acked_at - activated_at)) AS ack_s,"
        " avg(extract(epoch FROM cleared_at - activated_at)) AS clear_s FROM alarm_occurrence"
        " WHERE activated_at >= %s", (since,))[0]
    return {"windowMinutes": window_min, "annunciated": total,
            "ratePer10Min": {"average": round(total / periods, 2), "peak": max(buckets, default=0)},
            "floodPeriodShare": round(sum(n > catalog.flood_per_10min for n in buckets) / periods, 3),
            **_standing(engine),
            "badActors": [{**a, "share": round(a["activations"] / all_activations, 3)} for a in actors],
            "chattering": chatter,
            "priorityDistribution": {p["priority"]: p["n"] for p in priorities},
            "meanTimeToAckS": _round(response["ack_s"]), "meanTimeToClearS": _round(response["clear_s"])}


def _standing(engine: AlarmEngine) -> dict:
    now, stale_after = time.time(), engine.catalog.stale_after_s
    with engine.lock:
        active = [a for a in engine.alarms.values() if a.active]
        return {"standing": len(active),
                "stale": sum(1 for a in active if a.activated_at and now - a.activated_at > stale_after),
                "shelved": sum(1 for a in engine.alarms.values() if a.shelved_until is not None),
                "suppressed": sum(1 for a in engine.alarms.values() if a.state == "DSUPR"),
                "unacknowledged": sum(1 for a in engine.alarms.values() if a.state in ("UNACK", "RTNUN"))}


def _range(params: dict) -> tuple[datetime, datetime]:
    since = params.get("since")
    until = params.get("until")
    start = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else ts(time.time() - 86400)
    end = datetime.fromisoformat(until.replace("Z", "+00:00")) if until else ts(time.time() + 86400)
    return start, end


def _limit(params: dict) -> int:
    return max(1, min(5000, int(params.get("limit", 200))))


def _round(value) -> float | None:
    return None if value is None else round(float(value), 1)
