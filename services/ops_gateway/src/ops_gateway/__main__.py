"""Entry point: python -m ops_gateway (configuration via environment variables, see
docs/interfaces/services.md). Topics are resolved from the AAS (ADR-0020), not from the UNS registry."""

from __future__ import annotations

import logging
import os
import threading

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import broker_address

from .gateway import LineGateway
from .server import serve
from .watch import ConfigWatcher


def main() -> None:
    env = os.environ.get
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    host, port = broker_address(env("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-ops-gateway", host, port)
    gateway = LineGateway(mqtt)
    events = env("VF_AAS_EVENTS_TOPIC", "vf/basyx/submodelrepository/#") or None
    line_control = ids.submodel_id(env("VF_LINE", "LINE01"), "LineControl", "1")
    aas = BasyxClient(env("VF_AAS_URL", "http://localhost:8091"))
    watcher = ConfigWatcher(aas, line_control, gateway, events)
    gateway.on_other = watcher.on_message
    if events:
        mqtt.subscribe(events, qos=0)
    gateway.start()
    mqtt.start()
    threading.Thread(target=watcher.run, daemon=True, name="aas-config").start()
    http_port = int(env("VF_OPS_PORT", "8095"))
    logging.getLogger("ops-gateway").info("listening on :%d (LineControl %s)", http_port, line_control)
    serve(gateway, http_port).serve_forever()


if __name__ == "__main__":
    main()
