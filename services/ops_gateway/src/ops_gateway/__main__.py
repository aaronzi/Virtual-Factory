"""Entry point: python -m ops_gateway (configuration via environment variables, see
docs/interfaces/services.md). Topics are resolved from the AAS (ADR-0020), not from the UNS registry;
endpoints of an OPC UA interface are called over OPC UA (ADR-0024, VF_OPCUA_ENDPOINTS rewrites the AID
server address)."""

from __future__ import annotations

import logging
import os
import threading

from vf_common import ids
from vf_common.mqtt import MqttClient
from vf_common.registry_aas import RegistryAas
from vf_common.resolver import AasResolver, until_resolved
from vf_common.uns import broker_address

from .gateway import LineGateway
from .opcua_link import OpcUaLink
from .server import serve
from .watch import ConfigWatcher


def main() -> None:
    env = os.environ.get
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    host, port = broker_address(env("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-ops-gateway", host, port)
    logging.getLogger("asyncua").setLevel(logging.ERROR)
    opcua = OpcUaLink(lambda name, value: gateway.on_value(name, value))
    gateway = LineGateway(mqtt, opcua=opcua)
    opcua.start()
    events = env("VF_AAS_EVENTS_TOPIC", "vf/basyx/submodelrepository/#") or None
    # LineControl is located from the line's asset id via discovery + registry (ADR-0023)
    line_asset = env("VF_LINE_ASSET_ID", ids.asset_id(env("VF_LINE", "LINE01")))
    resolver = AasResolver.from_env()
    watcher = ConfigWatcher(RegistryAas(resolver), "", gateway, events)

    def on_other(msg):
        resolver.on_event(msg.topic, msg.payload)
        watcher.on_message(msg)

    def configure() -> None:
        watcher.line_control_id = until_resolved(
            lambda: resolver.submodel_of_asset(line_asset, "LineControl").id, f"LineControl of {line_asset}")
        watcher.run()

    gateway.on_other = on_other
    if events:
        mqtt.subscribe(events, qos=0)
    gateway.start()
    mqtt.start()
    threading.Thread(target=configure, daemon=True, name="aas-config").start()
    http_port = int(env("VF_OPS_PORT", "8095"))
    logging.getLogger("ops-gateway").info("listening on :%d (line asset %s)", http_port, line_asset)
    serve(gateway, http_port).serve_forever()


if __name__ == "__main__":
    main()
