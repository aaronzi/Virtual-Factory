"""Entry point: python -m alarms (configuration via environment variables, see
docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os
import threading
import time

from vf_common.http_api import serve
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns, broker_address

from .api import router
from .catalog import Catalog
from .db import Database
from .lifecycle import AlarmEngine
from .service import AlarmService

log = logging.getLogger("alarms")
ENV = os.environ.get


def main() -> None:
    logging.basicConfig(level=ENV("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    catalog = Catalog.load()
    db = Database(ENV("VF_ALARMS_DB", "postgresql://vf_alarms:vf-local-only@localhost:5433/alarms"))
    db.connect()
    db.init_schema(catalog)
    service = AlarmService(AlarmEngine(catalog), db, Uns.load())
    service.restore()
    port = int(ENV("VF_ALARMS_PORT", "8099"))
    threading.Thread(target=serve(router(service), port).serve_forever, daemon=True, name="http").start()
    host, mqtt_port = broker_address(ENV("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-alarms", host, mqtt_port)
    for topic in service.subscriptions():
        mqtt.subscribe(topic, qos=1)
    mqtt.start()
    log.info("alarms service on :%d, %d alarms in the master database", port, len(catalog.alarms))
    next_expiry = 0.0
    while True:
        msg = mqtt.get(timeout=0.5)
        try:
            if msg:
                service.handle(msg)
            if time.monotonic() >= next_expiry:
                next_expiry = time.monotonic() + 1.0
                service.expire()
        except Exception as exc:  # noqa: BLE001 - a bad message or a database hiccup must not stop the server
            log.warning("message on %s failed: %s", msg.topic if msg else "-", exc)


if __name__ == "__main__":
    main()
