"""Entry point: python -m maintenance (configuration via environment variables and infra/maintenance.json, see
docs/interfaces/services.md#maintenance).

    every 10 s          history of each monitored component (historian SQL) -> health index, RUL -> UNS
                        {root}/maintenance/{component}/..., AAS ConditionMonitoring; maintenance order
                        when due
    BPMN external tasks MaintenanceOrder (maintenance-*): ERP window, LineControl Maintain/SetUnitMode, record
    UNS                 session birth; device outputs of the components (latest values, reset confirmation)
    HTTP :8094          /health, /api/components, /api/orders, /api/settings
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from pathlib import Path

from vf_common import ids
from vf_common.aas.templates import TemplateLibrary
from vf_common.bpmn import BpmnClient
from vf_common.bpmn_worker import Worker
from vf_common.historian import HistorianConfig, InfluxClient
from vf_common.http_api import serve
from vf_common.mqtt import MqttClient
from vf_common.registry_aas import RegistryAas
from vf_common.resolver import AasResolver, until_resolved
from vf_common.uns import Uns, broker_address, now_iso, telemetry_value

from .advice import iso_ms
from .api import router
from .condition_aas import ConditionAas
from .config import Config
from .history import History
from .monitor import ComponentState, Monitor
from .orders import MaintenanceOrders
from .workflow import ErpWindows, LineControl, MaintenanceHandlers

log = logging.getLogger("maintenance")
ENV = os.environ.get
REPO = Path(os.environ.get("VF_REPO") or Path(__file__).resolve().parents[4])


class MaintenanceService:
    def __init__(self):
        self.config = Config.load()
        self.uns = Uns.load()
        self.bpmn_url = ENV("VF_BPMN_URL", "http://localhost:8092/engine-rest")
        self.resolver = AasResolver.from_env()
        self.aas = RegistryAas(self.resolver)
        self.condition = ConditionAas(self.aas, TemplateLibrary(REPO / "aas" / "templates"))
        self.orders = MaintenanceOrders(BpmnClient(self.bpmn_url))
        host, port = broker_address(ENV("VF_MQTT_URL", "mqtt://localhost:1883"))
        self.mqtt = MqttClient("vf-maintenance", host, port)
        influx = InfluxClient(ENV("VF_INFLUX_URL", "http://localhost:8181"), HistorianConfig.load().database)
        self.history = History(influx, self.config.max_points)
        self.monitor: Monitor | None = None
        self._line_control = ""

    def manufacturer_data(self) -> Monitor:
        """Maintenance tasks and design reliability of the components from their AAS (waits until
        resolvable)."""
        tasks, designs = {}, {}
        for c in self.config.components:
            tasks[c.tag] = until_resolved(lambda c=c: self.condition.task(c.tag, c.maintenance_task),
                                          f"{c.tag} MaintenanceInstructions")
            designs[c.tag] = until_resolved(lambda c=c: self.condition.design(c.tag, c.reliability_set),
                                            f"{c.tag} Reliability")
            log.info("%s: task %s (%s), design %s", c.tag, tasks[c.tag].maintenance_id, tasks[c.tag].name_en,
                     designs[c.tag])
        states = Monitor.states_for(self.config, tasks, designs)
        monitor = Monitor(self.config, self.history, states, self.publish, self.orders.open)
        monitor.on_evaluated = self.write_aas
        return monitor

    def publish(self, tag: str, indicator: str, value, t: float | None) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        topic = self.uns.maintenance(tag, indicator) if tag else self.uns.maintenance_alarm_topic
        ts = iso_ms(t) if t is not None else now_iso()
        self.mqtt.publish(topic, {"v": value, "ts": ts}, qos=1, retain=True)

    def write_aas(self, state: ComponentState) -> None:
        try:
            self.condition.update(state, self.monitor.recommendation(state),
                                  self.config.policy.rul_hours_threshold)
        except Exception as exc:  # noqa: BLE001 - AAS server busy: written again at the next evaluation
            log.warning("%s ConditionMonitoring not updated: %s", state.component.tag, exc)

    def line_control(self) -> str:
        if not self._line_control:
            self._line_control = self.resolver.submodel_of_asset(ids.asset_id("LINE01"), "LineControl").id
        return self._line_control

    def start_workers(self) -> None:
        erp = ErpWindows(ENV("VF_ERP_URL", "http://localhost:8098"))
        line = LineControl(self.aas, self.line_control)
        handlers = MaintenanceHandlers(self.monitor, line, erp, self.condition)
        Worker(BpmnClient(self.bpmn_url), "order", handlers.topics(), retries=40, service="maintenance",
               retry_timeout_ms=15000).start()
        for tag, order in until_resolved(self.orders.running, "running MaintenanceOrder instances").items():
            self.monitor.adopt(tag, order)

    def subscribe(self) -> dict[str, tuple[str, str]]:
        topics = {self.uns.telemetry(c.device, v): (c.device, v)
                  for c in self.config.components for v in c.variables}
        for topic in [self.uns.session_topic, *topics]:
            self.mqtt.subscribe(topic, qos=1)
        return topics

    def run(self) -> None:
        self.monitor = self.manufacturer_data()
        self.start_workers()
        port = int(ENV("VF_MAINTENANCE_PORT", "8094"))
        server = serve(router(self.monitor), port)
        threading.Thread(target=server.serve_forever, daemon=True, name="http").start()
        topics = self.subscribe()
        self.mqtt.start()
        log.info("maintenance service on :%d, monitoring %s", port, ", ".join(self.monitor.states))
        next_eval = 0.0
        while True:
            msg = self.mqtt.get(timeout=0.5)
            if msg and msg.topic == self.uns.session_topic:
                self.monitor.session = (msg.json() or {}).get("id") or self.monitor.session
            elif msg and msg.topic in topics:
                self.monitor.on_value(*topics[msg.topic], telemetry_value(msg.payload))
            if time.monotonic() >= next_eval:
                next_eval = time.monotonic() + self.config.interval_s
                try:
                    self.monitor.evaluate_all()
                except Exception as exc:  # noqa: BLE001 - keep monitoring
                    log.warning("evaluation failed: %s", exc)


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    MaintenanceService().run()


if __name__ == "__main__":
    main()
