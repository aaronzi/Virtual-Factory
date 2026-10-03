"""Maintenance windows: capacity reservations of plant maintenance on LINE01 (like a PM order reserving the
work center in an ERP), requested by the maintenance service for an open maintenance order (ADR-0029).

While a window is open the ERP releases no production order, so the line stays free for the maintenance:

    Requested  waiting for the order boundary: the running order is finished first (start OrderBoundary)
    Active     the line is free - no released order (OrderBoundary) or immediately (start Immediate: the
               running order is interrupted and resumed after the maintenance)
    Completed  the maintenance handed the line back; releases continue
    Cancelled  withdrawn without maintenance

REST (api.py): GET/POST /api/maintenance-windows, GET /api/maintenance-windows/{id},
POST /api/maintenance-windows/{id}/complete | /cancel. Requests are idempotent per maintenance order.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from vf_common.http_api import ApiError, Request, Response, Router

from .store import now_iso

# who may open / close maintenance windows (secure profile, ADR-0027)
WINDOW_ROLES = ("planner", "maintenance", "svc-maintenance")

STARTS = ("OrderBoundary", "Immediate")
OPEN = ("Requested", "Active")


@dataclass
class MaintenanceWindow:
    id: str
    maintenance_order: str
    start: str
    reason: str = ""
    line: str = "LINE01"
    state: str = "Requested"
    requested: str = field(default_factory=now_iso)
    activated: str | None = None
    completed: str | None = None
    interrupted_order: str | None = None  # order running when an Immediate window became active

    def to_dict(self) -> dict:
        return {"ID": self.id, "MaintenanceOrder": self.maintenance_order, "Line": self.line,
                "Start": self.start, "Reason": self.reason, "State": self.state, "Requested": self.requested,
                "Activated": self.activated, "Completed": self.completed,
                "InterruptedOrder": self.interrupted_order}


class MaintenanceWindows:
    def __init__(self):
        self.windows: dict[str, MaintenanceWindow] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def request(self, maintenance_order: str, start: str = "OrderBoundary",
                reason: str = "") -> MaintenanceWindow:
        if start not in STARTS:
            raise ValueError(f"start must be one of {', '.join(STARTS)}")
        if not maintenance_order:
            raise ValueError("maintenanceOrder is required")
        with self._lock:
            existing = next((w for w in self.windows.values()
                             if w.maintenance_order == maintenance_order and w.state in OPEN), None)
            if existing:
                return existing
            self._seq += 1
            window = MaintenanceWindow(f"MW-{self._seq:04d}", maintenance_order, start, reason)
            self.windows[window.id] = window
            return window

    def blocking(self) -> list[MaintenanceWindow]:
        """Open windows: no production order may be released."""
        with self._lock:
            return [w for w in self.windows.values() if w.state in OPEN]

    def update(self, open_orders: list) -> None:
        """Planning step: a requested window becomes active at the order boundary (or at once)."""
        with self._lock:
            for w in self.windows.values():
                if w.state == "Requested" and (w.start == "Immediate" or not open_orders):
                    w.state, w.activated = "Active", now_iso()
                    w.interrupted_order = open_orders[0].id if open_orders else None

    def close(self, window_id: str, state: str) -> MaintenanceWindow:
        with self._lock:
            window = self.windows.get(window_id)
            if window is None:
                raise KeyError(window_id)
            if window.state in OPEN:
                window.state, window.completed = state, now_iso()
            return window


def add_routes(r: Router, windows: MaintenanceWindows, store) -> None:
    def create(q: Request) -> Response:
        body = q.body or {}
        try:
            window = windows.request(str(body.get("maintenanceOrder") or ""),
                                     str(body.get("start") or "OrderBoundary"), str(body.get("reason") or ""))
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        windows.update(store.open_orders())
        return Response(201, window.to_dict())

    def one(q: Request, state: str | None = None) -> dict:
        try:
            if state:
                return windows.close(q.match["id"], state).to_dict()
            return windows.windows[q.match["id"]].to_dict()
        except KeyError as exc:
            raise ApiError(404, f"unknown maintenance window {q.match['id']}") from exc

    r.add("GET", "/api/maintenance-windows", lambda q: [w.to_dict() for w in windows.windows.values()])
    r.add("POST", "/api/maintenance-windows", create, WINDOW_ROLES)
    r.add("GET", r"/api/maintenance-windows/(?P<id>[\w-]+)", one)
    r.add("POST", r"/api/maintenance-windows/(?P<id>[\w-]+)/complete", lambda q: one(q, "Completed"),
          WINDOW_ROLES)
    r.add("POST", r"/api/maintenance-windows/(?P<id>[\w-]+)/cancel", lambda q: one(q, "Cancelled"),
          WINDOW_ROLES)
