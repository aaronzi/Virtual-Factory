"""Entry point: python -m edge - the edge connector (ADR-0024): subscribes to the OPC UA servers described in
the AIDs on the AAS server and publishes to the UNS; forwards UNS commands as OPC UA method calls.

Environment: VF_AAS_URL, VF_MQTT_URL, VF_OPCUA_ENDPOINTS (endpoint rewriting, see vf_common.opcua_client),
VF_EDGE_PUBLISHING_MS (default: telemetry.min_interval_s of the UNS registry), VF_AAS_EVENTS_TOPIC (BaSyx
change events: a changed AID re-configures the connector), LOG_LEVEL."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from vf_common.basyx import BasyxClient
from vf_common.mqtt import Message, MqttClient
from vf_common.uns import Uns, broker_address

from .config import AssetLink, resolve
from .connector import Connector

log = logging.getLogger("edge")


class Edge:
    def __init__(self, aas: BasyxClient, mqtt: MqttClient, publishing_ms: float, events_topic: str | None,
                 retry_s: float = 5.0):
        self.aas, self.mqtt, self.publishing_ms, self.retry_s = aas, mqtt, publishing_ms, retry_s
        self.events_prefix = events_topic.rstrip("#") if events_topic else None
        self.connectors: list[Connector] = []
        self._reload = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()  # strong references (the loop keeps only weak ones)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._spawn(self._dispatch(loop))
        self._spawn(self._report())
        while True:
            links = await self._resolve(loop)
            self.connectors = [Connector(link, self.mqtt, self.publishing_ms) for link in links]
            for connector in self.connectors:
                self._spawn(connector.start())
            await self._reload.wait()
            self._reload.clear()
            log.info("AID changed: re-configuring")
            for connector in self.connectors:
                await connector.stop()

    async def _resolve(self, loop) -> list[AssetLink]:
        while True:
            try:
                links = await loop.run_in_executor(None, resolve, self.aas)
            except Exception as exc:  # noqa: BLE001 - AAS server unreachable or still preloading
                log.error("cannot read the AIDs from the AAS server (%s); retrying in %.0f s", exc,
                          self.retry_s)
                await asyncio.sleep(self.retry_s)
                continue
            if links:
                return links
            log.warning("no AID with an OPC UA and an MQTT interface found; retrying in %.0f s", self.retry_s)
            await asyncio.sleep(self.retry_s)

    async def _dispatch(self, loop) -> None:
        """MQTT messages (queued by the network thread): commands and BaSyx change events."""
        while True:
            msg: Message | None = await loop.run_in_executor(None, self.mqtt.get, 0.5)
            if msg is None:
                continue
            if self.events_prefix and msg.topic.startswith(self.events_prefix):
                self._on_aas_event(msg)
                continue
            for connector in self.connectors:
                if await connector.handle_command(msg):
                    break

    def _on_aas_event(self, msg: Message) -> None:
        try:
            submodel = (json.loads(msg.payload).get("data") or {}).get("submodelId")
        except (ValueError, AttributeError):
            return
        if any(c.link.aid_id == submodel for c in self.connectors):
            self._reload.set()

    async def _report(self, every_s: float = 60.0) -> None:
        while True:
            await asyncio.sleep(every_s)
            for c in self.connectors:
                stats, c.stats = c.stats, {"telemetry": 0, "events": 0, "commands": 0, "command_ms": 0.0}
                mean = stats["command_ms"] / stats["commands"] if stats["commands"] else 0.0
                log.info("%s: %.1f telemetry msgs/s, %d events, %d commands (mean call %.1f ms)%s",
                         c.session.endpoint, stats["telemetry"] / every_s, stats["events"], stats["commands"],
                         mean, "" if c.healthy else " - no valid data from the server")


def main() -> None:
    env = os.environ.get
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncua").setLevel(logging.ERROR)
    host, port = broker_address(env("VF_MQTT_URL", "mqtt://localhost:1883"))
    mqtt = MqttClient("vf-edge", host, port)
    events = env("VF_AAS_EVENTS_TOPIC", "vf/basyx/submodelrepository/#") or None
    if events:
        mqtt.subscribe(events, qos=0)
    mqtt.start()
    default_ms = float(Uns.load().config["telemetry"].get("min_interval_s", 0.1)) * 1000.0
    edge = Edge(BasyxClient(env("VF_AAS_URL", "http://localhost:8091")), mqtt,
                float(env("VF_EDGE_PUBLISHING_MS", default_ms)), events)
    asyncio.run(edge.run())


if __name__ == "__main__":
    main()
