"""Entry point: python -m ops_gateway (configuration via environment variables, see
docs/interfaces/services.md)."""

from __future__ import annotations

import logging
import os

from vf_common.mqtt import MqttClient
from vf_common.uns import Uns, broker_address

from .gateway import LineGateway
from .server import serve


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    host, port = broker_address(os.environ.get("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-ops-gateway", host, port)
    gateway = LineGateway(mqtt, Uns.load(), controller=os.environ.get("VF_CONTROLLER", "PLC01"))
    gateway.start()
    mqtt.start()
    http_port = int(os.environ.get("VF_OPS_PORT", "8095"))
    logging.getLogger("ops-gateway").info("listening on :%d", http_port)
    serve(gateway, http_port).serve_forever()


if __name__ == "__main__":
    main()
