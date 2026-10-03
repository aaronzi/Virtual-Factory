"""Entry point: python -m sustainability (configuration via environment variables, see
docs/interfaces/services.md).

    BPMN external task pcf-calculate  -> production-based PCF of a packed part -> workpiece CarbonFootprint
                                         (purchased components: supplier batch AAS, federated discovery)
    UNS session birth                 -> new session: MeasurementStart, loss allocation and KPIs reset
    every 10 s                        -> OperationalCO2eq per device, LINE01 energy totals (plant_data.py)
    HTTP :8097                        -> /health, /api/kpis, /api/footprints[/<serial>]
"""

from __future__ import annotations

import logging
import os
import threading
import time

from provisioner.build import BuildContext, load_assets
from vf_common.basyx import BasyxClient
from vf_common.bpmn import BpmnClient
from vf_common.bpmn_worker import Worker
from vf_common.historian import HistorianConfig, InfluxClient
from vf_common.http_api import Guard, Response, Router, serve
from vf_common.mqtt import MqttClient
from vf_common.resolver import AasResolver
from vf_common.uns import Uns, broker_address

from .carbon import EnergyIntensity, FootprintCalculator
from .footprint_aas import FootprintWriter
from .handlers import FootprintHandlers
from .kpis import SessionKpis
from .plant_data import PlantData
from .process_energy import ProcessEnergy, power_tables
from .supplier_batches import SupplierBatchFootprints
from .suppliers import ChainedFootprints, ComponentTypeFootprints

log = logging.getLogger("sustainability")
ENV = os.environ.get


class Sustainability:
    def __init__(self):
        self.aas_url = ENV("VF_AAS_URL", "http://localhost:8091")
        self.uns = Uns.load()
        self.bpmn = BpmnClient(ENV("VF_BPMN_URL", "http://localhost:8092/engine-rest"))
        self.ctx = BuildContext()
        self.intensity = EnergyIntensity()
        self.plant = PlantData(BasyxClient(self.aas_url), self.intensity)
        self.kpis = SessionKpis()
        influx = InfluxClient(ENV("VF_INFLUX_URL", "http://localhost:8181"), HistorianConfig.load().database)
        energy = ProcessEnergy(influx, power_tables(load_assets(self.ctx.repo / "aas" / "data")))
        # supplier batch AAS via federated discovery (VF_AAS_REGISTRIES, ADR-0028), else the declared type PCF
        suppliers = ChainedFootprints(SupplierBatchFootprints(AasResolver.from_env()),
                                      ComponentTypeFootprints(BasyxClient(self.aas_url)))
        self.calculator = FootprintCalculator(self.aas_url, energy, self.intensity, suppliers)
        self.session: str | None = None

    def wait_for_aas(self) -> None:
        while True:
            try:
                if BasyxClient(self.aas_url).list_shells(limit=1) is not None:
                    self.calculator.static()  # BoM, emission factor, specific energy of compressed air
                    return
            except Exception as exc:  # noqa: BLE001 - server starting / preload still running
                log.info("waiting for the AAS server: %s", exc)
            time.sleep(3)

    def router(self) -> Router:
        router = Router(Guard.from_env())
        router.add("GET", "/health", lambda r: {"status": "ok", "session": self.session,
                                                "footprints": len(self.kpis.parts)}, public=True)
        router.add("GET", "/api/kpis", lambda r: self.kpis.values(self.plant.latest))
        router.add("GET", "/api/footprints", lambda r: self.kpis.recent(int(r.params.get("limit", 50))))
        router.add("GET", r"/api/footprints/(?P<serial>[\w-]+)", self._footprint)
        return router

    def _footprint(self, request) -> dict | Response:
        found = self.kpis.get(request.match["serial"])
        return found if found else Response(404, {"error": "no footprint for this serial in this session"})

    def on_session(self, birth: dict) -> None:
        session = birth.get("id")
        if not session or session == self.session:
            return
        self.session = session
        self.kpis.reset(session)
        self.plant.discover()
        self.plant.new_session(time.monotonic())
        log.info("new factory session %s", session)

    def run(self) -> None:
        port = int(ENV("VF_SUSTAINABILITY_PORT", "8097"))
        threading.Thread(target=serve(self.router(), port).serve_forever, daemon=True, name="http").start()
        self.wait_for_aas()
        self.plant.discover()
        writer = FootprintWriter(BasyxClient(self.aas_url), self.ctx)
        handlers = FootprintHandlers(self.calculator, writer, self.kpis)
        Worker(self.bpmn, "pcf", handlers.topics(), service="sustainability").start()
        host, mqtt_port = broker_address(ENV("VF_MQTT_URL", "mqtt://localhost:1883"))
        mqtt = MqttClient("vf-sustainability", host, mqtt_port)
        mqtt.subscribe(self.uns.session_topic, qos=1)
        mqtt.start()
        log.info("listening on :%d, worker for pcf-calculate started", port)
        next_sample = 0.0
        while True:
            msg = mqtt.get(timeout=0.5)
            if msg and msg.topic == self.uns.session_topic and isinstance(msg.json(), dict):
                self.on_session(msg.json())
            now = time.monotonic()
            if now >= next_sample:
                next_sample = now + 10.0
                try:
                    self.plant.sample(now)
                except Exception as exc:  # noqa: BLE001 - e.g. AAS server busy; next period retries
                    log.warning("plant data sample failed: %s", exc)


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    Sustainability().run()


if __name__ == "__main__":
    main()
