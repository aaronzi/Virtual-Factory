"""UNS events -> BPMN messages and MES reactions.

    part_released        -> message PartReleased  (starts WorkpieceLifecycle, business key = serial)
    part_inspected       -> message PartInspected (correlated by serial)
    part_sorted          -> message PartSorted    (correlated by serial)
    container_full       -> message ContainerFull (all ProductionOrder instances waiting for it)
    container_exchanged  -> KLT contents cleared in the AAS
    session birth        -> new session: workpiece AAS, workpiece processes and KLT contents reset

A message can arrive before the process instance waits for it (the previous task is still running), so failed
correlations are retried for up to `retry_s` seconds."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vf_common.uns import Uns

from .bpmn import BpmnClient

log = logging.getLogger("mes.events")
CONTAINER_TAG = {1: "KLTA01", 2: "KLTB01"}
TAG_CONTAINER = {v: k for k, v in CONTAINER_TAG.items()}


@dataclass
class _Pending:
    message: str
    key: str | None
    variables: dict
    all_instances: bool
    first: float
    next_try: float


def message_for(event: dict) -> tuple[str, str | None, dict, bool] | None:
    """(message name, business key, process variables, correlate to all) for a UNS event, or None."""
    name, ts = event.get("event"), event.get("ts")
    if name == "part_released":
        return "PartReleased", event["serial"], {
            "serial": event["serial"], "releasedAt": ts, "session": event.get("session"),
            "leakRate": float(event.get("leak_rate", 0)),
            "strokeTime": float(event.get("stroke_time", 0))}, False
    if name == "part_inspected" and event.get("serial"):
        return "PartInspected", event["serial"], {
            "inspectedAt": ts, "plcResult": int(event.get("result", 0)),
            "deltaE": float(event.get("delta_e", 0)),
            "hue": float(event.get("hue", 0)), "r": float(event.get("r", 0)), "g": float(event.get("g", 0)),
            "b": float(event.get("b", 0))}, False
    if name == "part_sorted" and event.get("serial"):
        return "PartSorted", event["serial"], {
            "sortedAt": ts, "container": int(event.get("container", 0)),
            "slot": int(event.get("slot", 0))}, False
    if name == "container_full":
        return "ContainerFull", None, {"container": TAG_CONTAINER.get(event.get("device"), 0)}, True
    return None


class EventRouter:
    def __init__(self, bpmn: BpmnClient, uns: Uns, on_session, on_exchange, retry_s: float = 60.0):
        self.bpmn, self.uns, self.on_session, self.on_exchange = bpmn, uns, on_session, on_exchange
        self.retry_s = retry_s
        self.pending: list[_Pending] = []
        self.session: str | None = None
        self.correlated = 0

    def handle(self, topic: str, event: dict, now: float) -> None:
        if topic == self.uns.session_topic:
            self._session(event)
            return
        if event.get("event") == "container_exchanged":
            self.on_exchange(event.get("device"), int(event.get("exchange_count", 0)))
            return
        message = message_for(event)
        if message:
            self._correlate(_Pending(message[0], message[1], message[2], message[3], now, now), now)

    def retry(self, now: float) -> None:
        due, self.pending = [p for p in self.pending if p.next_try <= now], [p for p in self.pending
                                                                              if p.next_try > now]
        for p in due:
            self._correlate(p, now)

    def _correlate(self, p: _Pending, now: float) -> None:
        try:
            ok = self.bpmn.correlate(p.message, p.key, p.variables, p.all_instances)
        except Exception as exc:  # noqa: BLE001 - engine unavailable: retry like a missing subscription
            log.warning("correlate %s %s: %s", p.message, p.key, exc)
            ok = False
        if ok:
            self.correlated += 1
        elif p.all_instances:
            log.debug("%s: no waiting instance", p.message)  # e.g. no production order running
        elif now - p.first < self.retry_s:
            p.next_try = now + 1.0
            self.pending.append(p)
        else:
            log.warning("%s for %s dropped after %.0f s (no waiting process instance)", p.message, p.key,
                        self.retry_s)

    def _session(self, birth: dict) -> None:
        session = birth.get("id")
        if session and session != self.session:
            previous, self.session = self.session, session
            self.pending.clear()
            log.info("new factory session %s (previous %s)", session, previous)
            self.on_session(session, birth)
