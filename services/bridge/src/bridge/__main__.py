"""Entry point: python -m bridge (configuration via environment variables, see
docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os
import time

from vf_common.basyx import BasyxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import broker_address

from .service import Bridge


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    host, port = broker_address(os.environ.get("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-bridge", host, port)
    mqtt.start()
    aas = BasyxClient(os.environ.get("VF_AAS_URL", "http://localhost:8091"))
    while True:  # the AAS server may still be importing its preload
        try:
            aas.list_submodels(limit=1)
            break
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("bridge").info("waiting for AAS server: %s", exc)
            time.sleep(3)
    events = os.environ.get("VF_AAS_EVENTS_TOPIC", "vf/basyx/submodelrepository/#") or None
    Bridge(aas, mqtt, events, min_interval=float(os.environ.get("VF_BRIDGE_MIN_INTERVAL", "5.0"))).run()


if __name__ == "__main__":
    main()
