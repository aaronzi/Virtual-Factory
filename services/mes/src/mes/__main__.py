"""Entry point: python -m mes (configuration via environment variables, see docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os
import time

from provisioner.build import BuildContext, load_assets
from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.bpmn import BpmnClient
from vf_common.bpmn_worker import Worker
from vf_common.mqtt import MqttClient
from vf_common.registry_aas import RegistryAas
from vf_common.resolver import AasResolver, until_resolved
from vf_common.uns import Uns, broker_address, telemetry_value

from .event_topics import EventTopics
from .events import EventRouter
from .handlers import OrderHandlers, WorkpieceHandlers
from .klt import CONTAINERS, KltContents
from .kpi import KpiTracker
from .orders import ActiveOrder, ErpClient
from .passport import bom_nodes
from .quality import Limits
from .staging import LotStaging
from .store import WorkpieceStore
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
        self.kpi = KpiTracker()
        self.klt = KltContents(BasyxClient(self.aas_url))
        self.kpi_aas = BasyxClient(self.aas_url)
        self.erp = ErpClient(ENV("VF_ERP_URL", ""))
        # AAS of other owners (line, PLC, device AIDs, product type) are located via discovery + registry
        # (ADR-0023); the MES writes its own AAS (workpieces, KLT contents, KPIs) into its repository.
        self.resolver = AasResolver.from_env()

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
        type_asset = type_spec["globalAssetId"]  # GS1 Digital Link of the product type
        product = until_resolved(lambda: self.resolver.resolve_asset(type_asset), "PC3280_TYPE")
        thumbnail = {"path": f"{product.href}/asset-information/thumbnail", "contentType": "image/png"}
        store = WorkpieceStore(self.ctx, aas, retention=int(ENV("VF_RETENTION", "500")),
                               passport_limit=int(ENV("VF_PASSPORT_LIMIT", "0")))
        self.store = store
        blueprint = load_blueprint()
        bulk = {n["_idShort"]: float(n["statements"]["BulkCount"]) for n in bom_nodes(blueprint)}
        order = ActiveOrder(bulk)
        workpieces = WorkpieceHandlers(store, WorkpieceSpec(blueprint, self.ctx.positions, thumbnail),
                                       Limits.from_recipe(recipe["values"]), KltContents(aas), order,
                                       LotStaging(ENV("VF_ERP_URL", "")))
        Worker(self.bpmn, "workpiece", workpieces.topics()).start()
        # order tasks wait for the line / the ERP: retried every 15 s for up to an hour before an incident
        orders = OrderHandlers(RegistryAas(self.resolver), order=order, erp=self.erp)
        orders.line_control = self._submodel("LINE01", "LineControl")
        orders.operational_data = self._submodel("PLC01", "OperationalData")
        Worker(BpmnClient(str(self.bpmn.http.base_url)), "order", orders.topics(),
               retries=240, retry_timeout_ms=15000).start()

    def _submodel(self, tag: str, id_short: str) -> str:
        """Submodel id of a device's AAS: asset id -> discovery -> registry (no id convention)."""
        asset = ids.asset_id(tag)  # the asset's own identifier (type plate)
        return until_resolved(lambda: self.resolver.submodel_of_asset(asset, id_short).id,
                              f"{tag} {id_short}")

    def on_session(self, session: str, birth: dict) -> None:
        removed, kept = self.store.clear_session()
        self.bpmn.delete_instances("WorkpieceLifecycle", f"new factory session {session}")
        for tag in CONTAINERS.values():
            self.klt.clear(tag, 0)
        self.kpi.reset()
        log.info("session %s: removed %d workpiece AAS of the previous session (session data), kept %d "
                 "passports of shipped units", session, removed, kept)

    def on_exchange(self, tag: str, count: int) -> None:
        self.klt.clear(tag, count)

    def run(self) -> None:
        self.wait_for_backends()
        self.bpmn.deploy("virtual-factory", sorted((self.ctx.repo / "bpmn").glob("*.bpmn")))
        self.start_workers()
        host, port = broker_address(ENV("VF_MQTT_URL", "mqtt://localhost:1883"))
        mqtt = MqttClient("vf-mes", host, port)
        # event topics from the AID event affordances (reloaded on AID changes), session from the registry
        topics = EventTopics(RegistryAas(self.resolver), mqtt,
                             ENV("VF_AAS_EVENTS_TOPIC", "vf/basyx/submodelrepository/#") or None)
        topics.reload()
        router = EventRouter(self.bpmn, self.uns, self.on_session, self.on_exchange, topics=topics)
        kpi_topics = {self.uns.telemetry("PLC01", v): v for v in ("packml_state", "parts_total", "parts_ok",
                                                                    "parts_nok")}
        for topic in [self.uns.session_topic, *kpi_topics]:
            mqtt.subscribe(topic, qos=1)
        mqtt.start()
        self._loop(mqtt, router, kpi_topics)

    def _loop(self, mqtt: MqttClient, router: EventRouter, kpi_topics: dict) -> None:
        next_kpi = 0.0
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
            next_kpi = self._periodic(now, next_kpi, 15.0, lambda t: self.kpi.write(self.kpi_aas, last_ts))

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
