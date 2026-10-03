"""REST API of the ERP simulator (port 8098), JSON with ISA-95 / B2MML naming:

    GET  /health
    GET  /api/materials                         material master (finished good, components with supplier)
    GET  /api/orders[?state=]                   production orders (OperationsRequest-like)
    POST /api/orders                            {"quantity", "material"?, "dueDate"?, "release"?} -> order
    GET  /api/orders/{id}
    POST /api/orders/{id}/release               release to the MES (BPMN message OrderReleased)
    POST /api/production-performance            confirmation of the MES (OperationsPerformance)
    GET  /api/batches                           component batches (goods receipts, consumption, stock)
    POST /api/goods-receipts                    {"material", "lot", "quantity"?} -> batch (quantity
                                                default: the supplier's despatch advice)
    POST /api/material-staging                  {"material", "lot"}: MES reports a lot staged at the line
                                                -> goods receipt from the despatch advice (once per lot)
    GET  /api/settings, PUT /api/settings       {"autoRelease", "standingQuantity", "rejectRateLimit", ...}
    GET  /api/maintenance-windows               maintenance windows (capacity reservations, maintenance.py)
    POST /api/maintenance-windows               {"maintenanceOrder", "start", "reason"}
                                                (start: OrderBoundary | Immediate)
    GET  /api/maintenance-windows/{id}, POST .../{id}/complete, POST .../{id}/cancel
    GET  /                                      status page
"""

from __future__ import annotations

from vf_common.http_api import ApiError, Guard, Request, Response, Router

from .maintenance import add_routes as add_maintenance_routes
from .page import status_page
from .receipts import GoodsReceipts
from .release import OrderRelease, Settings
from .store import ErpStore

PLANNER, MES = ("planner",), ("svc-mes",)  # roles of the write routes (secure profile, ADR-0027)


def router(store: ErpStore, release: OrderRelease, settings: Settings,
           receipts: GoodsReceipts | None = None) -> Router:
    receipts = receipts or GoodsReceipts(store)
    r = Router(Guard.from_env())
    r.add("GET", "/", lambda q: Response(200, status_page(), "text/html; charset=utf-8"))
    r.add("GET", "/health", lambda q: {"status": "ok", "orders": len(store.orders),
                                       "open": [o.id for o in store.open_orders()]}, public=True)
    r.add("GET", "/api/materials", lambda q: [m.to_dict() for m in store.materials.values()])
    r.add("GET", "/api/orders", lambda q: [o.to_b2mml() for o in store.orders.values()
                                           if not q.params.get("state") or o.state == q.params["state"]])
    r.add("POST", "/api/orders", lambda q: _create(store, release, q), PLANNER)
    r.add("GET", r"/api/orders/(?P<id>[\w-]+)", lambda q: _order(store, q.match["id"]).to_b2mml())
    r.add("POST", r"/api/orders/(?P<id>[\w-]+)/release",
          lambda q: _release(release, _order(store, q.match["id"])), PLANNER)
    r.add("POST", "/api/production-performance", lambda q: _confirm(store, q), MES)
    r.add("GET", "/api/batches", lambda q: [b.to_dict() for b in store.batches.values()])
    r.add("POST", "/api/goods-receipts", lambda q: Response(201, receipts.receive(
        str(q.body["material"]), str(q.body["lot"]),
        int(q.body["quantity"]) if q.body.get("quantity") is not None else None)), (*PLANNER, *MES))
    r.add("POST", "/api/material-staging", lambda q: _stage(receipts, q), MES)
    r.add("GET", "/api/settings", lambda q: settings.to_dict())
    r.add("PUT", "/api/settings", lambda q: _settings(settings, q), PLANNER)
    add_maintenance_routes(r, release.windows, store)
    return r


def _order(store: ErpStore, order_id: str):
    order = store.get(order_id)
    if order is None:
        raise ApiError(404, f"unknown order {order_id}")
    return order


def _create(store: ErpStore, release: OrderRelease, q: Request) -> Response:
    body = q.body or {}
    order = store.create_order(int(body["quantity"]), str(body.get("material") or "PC3280"),
                               body.get("dueDate"))
    if body.get("release"):
        _release(release, order)
    return Response(201, order.to_b2mml())


def _release(release: OrderRelease, order) -> dict:
    try:
        return release.release(order).to_b2mml()
    except RuntimeError as exc:
        raise ApiError(503, str(exc)) from exc
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


def _confirm(store: ErpStore, q: Request) -> dict:
    if "OperationsResponse" not in (q.body or {}):
        raise ApiError(400, "OperationsPerformance with OperationsResponse expected")
    try:
        return store.confirm(q.body).to_b2mml()
    except KeyError as exc:
        raise ApiError(404, f"unknown order {exc}") from exc


def _stage(receipts: GoodsReceipts, q: Request) -> Response:
    try:
        batch, created = receipts.stage(str(q.body["material"]), str(q.body["lot"]))
    except RuntimeError as exc:  # supplier portal unreachable: the MES reports the lot again
        raise ApiError(503, str(exc)) from exc
    return Response(201 if created else 200, batch)


def _settings(settings: Settings, q: Request) -> dict:
    settings.update(q.body or {})
    return settings.to_dict()
