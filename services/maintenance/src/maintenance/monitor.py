"""Condition monitoring of the configured components: every evaluation reads the history (historian), computes
the prognosis, decides on a maintenance order and publishes the results (UNS, AAS).

Order policy (config.Policy): open a maintenance order when
    - trend fit and the 90 % lower bound of the RUL in hours < rul_hours_threshold and
      HI < health_index_gate, or
    - HI < health_index_order, or
    - the device reports the failure (e.g. gripper_fault).
One open order per component; it is closed by the MaintenanceOrder process (record step). While an order is
open, the component's advisory alarm (infra/alarms.json, source MAINTENANCE) is in the alarm word.

Health state: Unknown (no data), Alarm (HI <= 0.05 or failure), Warning (order due or open), Good.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .advice import recommendation, summary
from .config import Component, Config
from .history import History, Readings
from .prognosis import Design, Prognosis, estimate
from .tasks import MaintenanceTask, fallback

log = logging.getLogger("maintenance.monitor")
ALARM_HI = 0.05

Publisher = Callable[[str, str, object, float | None], None]  # (component tag, indicator, value, time)
OrderOpener = Callable[[Component, MaintenanceTask, Prognosis, str], str]  # -> business key


@dataclass
class ComponentState:
    component: Component
    task: MaintenanceTask
    design: Design
    prognosis: Prognosis | None = None
    health: str = "Unknown"
    order: str = ""
    order_health_index: float | None = None
    live: dict = field(default_factory=dict)      # latest UNS values of the component's device outputs
    latest: dict = field(default_factory=dict)    # latest historian row (forward filled)
    evaluated: float = 0.0
    error: str = ""

    @property
    def faulted(self) -> bool:
        c = self.component
        value = self.live.get(c.fault, self.latest.get(c.fault)) if c.fault else False
        return value in (True, "true", 1)

    def value(self, variable: str):
        return self.live.get(variable, self.latest.get(variable))

    def to_dict(self) -> dict:
        c = self.component
        return {"component": c.tag, "device": c.device, "name": {"en": c.name_en, "de": c.name_de},
                "indicator": c.indicator, "unit": c.unit, "limit": c.limit, "healthState": self.health,
                "prognosis": self.prognosis.to_dict() if self.prognosis else None,
                "order": self.order or None,
                "maintenanceTask": self.task.maintenance_id or None, "faulted": self.faulted,
                "symptoms": {k: self.value(v) for k, v in c.symptoms.items()}, "error": self.error or None}


class Monitor:
    def __init__(self, config: Config, history: History, states: dict[str, ComponentState],
                 publish: Publisher, open_order: OrderOpener):
        self.config, self.history, self.states = config, history, states
        self.publish, self.open_order = publish, open_order
        self.session: str | None = None
        self.on_evaluated: Callable[[ComponentState], None] | None = None  # AAS update
        self._lock = threading.RLock()

    @classmethod
    def states_for(cls, config: Config, tasks: dict[str, MaintenanceTask],
                   designs: dict[str, Design]) -> dict[str, ComponentState]:
        return {c.tag: ComponentState(c, tasks.get(c.tag) or fallback(c.name_en),
                                      designs.get(c.tag) or Design(0.0)) for c in config.components}

    # -- inputs ----------------------------------------------------------------------------------------

    def on_value(self, device: str, variable: str, value) -> None:
        for state in self.states.values():
            if state.component.device.upper() == device.upper() and variable in state.component.variables:
                state.live[variable] = value

    def adopt(self, tag: str, order: str) -> None:
        """Running MaintenanceOrder instance found at start (the service was restarted)."""
        if tag in self.states:
            self.states[tag].order = order
            log.info("%s: adopted open maintenance order %s", tag, order)

    # -- evaluation ------------------------------------------------------------------------------------

    def evaluate_all(self) -> None:
        for tag in self.states:
            self.evaluate(tag)

    def evaluate(self, tag: str) -> ComponentState:
        with self._lock:
            state = self.states[tag]
            try:
                readings = self.history.readings(state.component, self.session)
                state.error = ""
            except Exception as exc:  # noqa: BLE001 - historian not reachable: keep the last result
                state.error = f"historian: {exc}"
                log.warning("%s: %s", tag, state.error)
                return state
            self.apply(state, readings)
            return state

    def apply(self, state: ComponentState, readings: Readings, now: float | None = None) -> None:
        c, cfg = state.component, self.config
        state.latest = readings.latest
        state.prognosis = estimate(readings.samples, c.limit, state.design, cfg.min_points,
                                   cfg.throughput_points)
        state.evaluated = time.time() if now is None else now
        due = self.order_due(state)
        if due and not state.order and state.prognosis is not None:
            self._open(state)
        state.health = self.health_of(state, due)
        self._publish(state)
        if self.on_evaluated:
            self.on_evaluated(state)

    def _open(self, state: ComponentState) -> None:
        c, p = state.component, state.prognosis
        try:
            state.order = self.open_order(c, state.task, p, summary(c, state.task, p))
        except Exception as exc:  # noqa: BLE001 - engine down / process not deployed: next evaluation retries
            log.warning("%s: maintenance order could not be opened: %s", c.tag, exc)
            return
        state.order_health_index = p.health_index
        log.info("%s: maintenance order %s opened (%s)", c.tag, state.order, p.to_dict())

    def order_due(self, state: ComponentState) -> bool:
        p, policy = state.prognosis, self.config.policy
        if state.faulted:
            return True
        if p is None:
            return False
        if p.health_index < policy.health_index_order:
            return True
        return (p.method == "TrendFit" and p.rul_hours_low is not None
                and p.health_index < policy.health_index_gate
                and p.rul_hours_low < policy.rul_hours_threshold)

    @staticmethod
    def health_of(state: ComponentState, due: bool) -> str:
        p = state.prognosis
        if p is None and not state.faulted:
            return "Unknown"
        if state.faulted or (p is not None and p.health_index <= ALARM_HI):
            return "Alarm"
        return "Warning" if due or state.order else "Good"

    def recommendation(self, state: ComponentState) -> dict[str, str]:
        return recommendation(state.health, state.component, state.task, state.prognosis, state.order)

    # -- orders ----------------------------------------------------------------------------------------

    def close_order(self, tag: str, order: str) -> None:
        with self._lock:
            state = self.states.get(tag)
            if state and state.order == order:
                state.order, state.order_health_index = "", None
                log.info("%s: maintenance order %s closed", tag, order)
        self.publish_alarms()

    def alarm_word(self) -> str:
        codes = sorted(s.component.alarm for s in self.states.values() if s.order and s.component.alarm)
        return ",".join(str(c) for c in codes)

    def publish_alarms(self) -> None:
        self.publish("", "active_alarms", self.alarm_word(), None)

    def _publish(self, state: ComponentState) -> None:
        p, tag = state.prognosis, state.component.tag
        values = {"health_state": state.health, "order": state.order}
        if p is not None:
            values |= {"health_index": p.health_index, "wear": p.value, "rul_cycles": p.rul_cycles,
                       "rul_cycles_low": p.rul_cycles_low, "rul_hours": p.rul_hours,
                       "rul_hours_low": p.rul_hours_low, "confidence": p.confidence,
                       "throughput": p.throughput}
        for indicator, value in values.items():
            self.publish(tag, indicator, value, p.time if p is not None else None)
        self.publish_alarms()
