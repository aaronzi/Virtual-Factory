"""REST API of the maintenance service (port 8094):

    GET  /health
    GET  /api/components                     condition of every monitored component (health, RUL, order)
    GET  /api/components/{tag}
    POST /api/components/{tag}/evaluate      evaluate now (instead of waiting for the next period)
    GET  /api/orders                         open maintenance orders {component: order}
    GET  /api/settings, PUT /api/settings    order policy {"rulHoursThreshold", "healthIndexGate",
                                             "healthIndexOrder"}
"""

from __future__ import annotations

from vf_common.http_api import ApiError, Request, Router

from .monitor import Monitor


def router(monitor: Monitor) -> Router:
    r = Router()
    r.add("GET", "/health", lambda q: {"status": "ok", "session": monitor.session,
                                       "components": sorted(monitor.states),
                                       "openOrders": _orders(monitor), "alarms": monitor.alarm_word()})
    r.add("GET", "/api/components", lambda q: [s.to_dict() for s in monitor.states.values()])
    r.add("GET", r"/api/components/(?P<tag>\w+)", lambda q: _state(monitor, q).to_dict())
    r.add("POST", r"/api/components/(?P<tag>\w+)/evaluate",
          lambda q: monitor.evaluate(_state(monitor, q).component.tag).to_dict())
    r.add("GET", "/api/orders", lambda q: _orders(monitor))
    r.add("GET", "/api/settings", lambda q: monitor.config.policy.to_dict())
    r.add("PUT", "/api/settings", lambda q: _settings(monitor, q))
    return r


def _orders(monitor: Monitor) -> dict:
    return {tag: s.order for tag, s in monitor.states.items() if s.order}


def _state(monitor: Monitor, q: Request):
    state = monitor.states.get(q.match["tag"].upper())
    if state is None:
        raise ApiError(404, f"unknown component {q.match['tag']} (monitored: {', '.join(monitor.states)})")
    return state


def _settings(monitor: Monitor, q: Request) -> dict:
    monitor.config.policy.update(q.body or {})
    return monitor.config.policy.to_dict()
