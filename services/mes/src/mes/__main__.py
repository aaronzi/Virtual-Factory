"""Entry point: python -m mes (configuration via environment variables, see docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os
import time

from provisioner.build import BuildContext, load_assets
from vf_common import ids
from vf_common.basyx import BasyxClient, b64
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns, broker_address, telemetry_value

from .bpmn import BpmnClient
from .carbon import EnergyIntensity, component_footprint
from .events import EventRouter
from .handlers import OrderHandlers, WorkpieceHandlers
from .klt import CONTAINERS, KltContents
from .kpi import KpiTracker
from .plant_data import PlantData
from .quality import Limits
from .store import WorkpieceStore
from .workers import Worker
from .workpiece import WorkpieceSpec, load_blueprint

log = logging.getLogger("mes")
ENV = os.environ.get


class Mes:
    def __init__(self):
        self.aas_url = ENV("VF_AAS_URL", "http://localhost:8091")
        self.uns = Uns.load()
        self.bpmn = BpmnClient(ENV("VF_BPMN_URL", "http://localhost:8092/engine-rest"))
        self.aas = BasyxClient(self.aas_url)
        self.ctx = BuildContext()
        self.intensity = EnergyIntensity()
        self.plant = PlantData(BasyxClient(self.aas_url), self.intensity)
        self.kpi = KpiTracker()
        self.klt = KltContents(BasyxClient(self.aas_url))
        self._components: float | None = None
        self._factor: float | None = None

    def wait_for_backends(self) -> None:
        """Waits for the engine and until the AAS server has finished its preload (shell count stable)."""
        previous, stable = -1, 0
        while stable < 3:
            try:
                count = len(self.aas.list_shells())
                ready = self.bpmn.engine_ready() and count > 0
                stable = stable + 1 if ready and count == previous else 0
                previous = count
            except Exception as exc:  # noqa: BLE001
                log.info("waiting for AAS server / BPMN engine: %s", exc)
                stable = 0
            time.sleep(3)

    def start_workers(self) -> None:
        aas = BasyxClient(self.aas_url)
        type_spec = load_assets(self.ctx.repo / "aas" / "data", {"PC3280_TYPE"})[0]
        recipe = next(s for s in type_spec["submodels"] if s["template"].startswith("ManufacturingRecipe"))
        public = ENV("VF_AAS_PUBLIC_URL", "http://localhost:8091")
        thumbnail = {"path": f"{public}/shells/{b64(ids.aas_id('PC3280_TYPE'))}/asset-information/thumbnail",
                     "contentType": "image/png"}
        store = WorkpieceStore(self.ctx, aas, retention=int(ENV("VF_RETENTION", "500")))
        self.store = store
        workpieces = WorkpieceHandlers(store, WorkpieceSpec(load_blueprint(), self.ctx.positions, thumbnail),
                                       Limits.from_recipe(recipe["values"]), KltContents(aas), self.footprint)
        Worker(self.bpmn, "workpiece", workpieces.topics()).start()
        Worker(BpmnClient(str(self.bpmn.http.base_url)), "order",
               OrderHandlers(BasyxClient(self.aas_url)).topics()).start()

    def footprint(self) -> float:
        """Instance PCF: BoM component PCFs (read once from the AAS) + line energy per part x grid factor."""
        if self._components is None:
            self._components = component_footprint(BasyxClient(self.aas_url))
            line_energy = ids.submodel_id("LINE01", "EnergyConsumption", "1")
            self._factor = float(BasyxClient(self.aas_url).get_value(line_energy, "EmissionFactor"))
            log.info("BoM component PCF %.4f kg CO2e, grid factor %.3f kg/kWh",
                     self._components, self._factor)
        return self._components + self.intensity.kwh_per_part * (self._factor or 0.0)

    def on_session(self, session: str, birth: dict) -> None:
        removed = self.store.clear_session()
        self.bpmn.delete_instances("WorkpieceLifecycle", f"new factory session {session}")
        for tag in CONTAINERS.values():
            self.klt.clear(tag, 0)
        self.plant.discover()
        self.plant.new_session(time.monotonic())
        self.kpi.reset()
        log.info("session %s: removed %d workpiece AAS of the previous session", session, removed)

    def on_exchange(self, tag: str, count: int) -> None:
        self.klt.clear(tag, count)

    def run(self) -> None:
        self.wait_for_backends()
        self.bpmn.deploy("virtual-factory", sorted((self.ctx.repo / "bpmn").glob("*.bpmn")))
        self.plant.discover()
        self.start_workers()
        host, port = broker_address(ENV("VF_MQTT_URL", "mqtt://localhost:1883"))
        mqtt = MqttClient("vf-mes", host, port)
        router = EventRouter(self.bpmn, self.uns, self.on_session, self.on_exchange)
        kpi_topics = {self.uns.telemetry("PLC01", v): v for v in ("packml_state", "parts_total", "parts_ok",
                                                                    "parts_nok")}
        for topic in [self.uns.all_events(), self.uns.session_topic, *kpi_topics]:
            mqtt.subscribe(topic, qos=1)
        mqtt.start()
        self._loop(mqtt, router, kpi_topics)

    def _loop(self, mqtt: MqttClient, router: EventRouter, kpi_topics: dict) -> None:
        next_sample = next_kpi = 0.0
        next_discover = time.monotonic() + 300
        last_ts = None
        while True:
            msg = mqtt.get(timeout=0.5)
            now = time.monotonic()
            if msg and msg.topic in kpi_topics:
                data = msg.json() or {}
                last_ts = data.get("ts") or last_ts
                if kpi_topics[msg.topic] == "packml_state" and last_ts:
                    self.kpi.on_state(int(telemetry_value(msg.payload)), last_ts)
                else:
                    self.kpi.on_counter(kpi_topics[msg.topic], int(telemetry_value(msg.payload) or 0))
            elif msg and isinstance(msg.json(), dict):
                router.handle(msg.topic, msg.json(), now)
            router.retry(now)
            next_sample = self._periodic(now, next_sample, 10.0, self.plant.sample)
            next_kpi = self._periodic(now, next_kpi, 15.0, lambda t: self.kpi.write(self.plant.aas, last_ts))
            next_discover = self._periodic(now, next_discover, 300.0, lambda t: self.plant.discover())

    @staticmethod
    def _periodic(now: float, due: float, interval: float, job) -> float:
        if now < due:
            return due
        try:
            job(now)
        except Exception as exc:  # noqa: BLE001 - e.g. AAS server busy; next period retries
            log.warning("periodic job failed: %s", exc)
        return now + interval


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    Mes().run()


if __name__ == "__main__":
    main()
