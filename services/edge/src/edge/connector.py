"""Bridges one controller (AssetLink) between its OPC UA server and the UNS (ADR-0024):

    monitored items  -> {root}/{device}/{variable}       {"v": value, "ts": SourceTimestamp}    retained
    OPC UA events    -> {root}/{device}/event/{event}    {"event", "device", "session", "seq", "ts", fields}
    UNS commands     -> OPC UA method call -> {root}/{device}/cmd-resp/{variable} {"corr", "accepted", ...}

Topics, QoS/retain and payload keys come from the MQTT affordances, nodes from the OPC UA affordances of the
same AID. Values with a bad status (BadNoCommunication: the PLC CPU is not linked to its communication module)
are not published, and the command topics are only subscribed while the server delivers good values - so the
edge never answers commands for a controller it cannot reach (and never competes with a directly publishing
simulation, `--vf-backplane=off`)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from asyncua import ua

from vf_common.mqtt import Message, MqttClient
from vf_common.opcua_client import UaSession, endpoint_map, rewrite, status_text
from vf_common.uns import now_iso

from .config import AssetLink, Route

log = logging.getLogger("edge")
STANDARD_FIELDS = {"Session": "session", "Seq": "seq"}


def iso(ts: datetime | None) -> str:
    if ts is None:
        return now_iso()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Connector:
    def __init__(self, link: AssetLink, mqtt: MqttClient, publishing_ms: float = 100.0,
                 mapping: dict[str, str] | None = None):
        self.link, self.mqtt, self.publishing_ms = link, mqtt, publishing_ms
        self.session = UaSession(rewrite(link.endpoint, endpoint_map() if mapping is None else mapping))
        self.commands = {r.uns.form.topic: r for r in link.actions}
        self.healthy = False
        self.stats = {"telemetry": 0, "events": 0, "commands": 0, "command_ms": 0.0}
        self._points: dict[ua.NodeId, Route] = {}
        self._event_types: dict[ua.NodeId, tuple[Route, list[str]]] = {}
        self._subscription = None

    async def start(self) -> None:
        """Connects (retrying) and subscribes; the asyncua client reconnects and re-subscribes by itself."""
        await self.session.connect()
        self.session.client.connection_lost_callback = self._connection_lost
        self._subscription = await self.session.client.create_subscription(self.publishing_ms, self)
        nodes = []
        for route in self.link.properties:
            node = await self.session.node(route.ua.form.topic)
            self._points[node.nodeid] = route
            nodes.append(node)
        if nodes:
            await self._subscription.subscribe_data_change(nodes, sampling_interval=0, queuesize=50)
        await self._subscribe_events()
        log.info("bridging %s", self.link.describe())

    async def stop(self) -> None:
        self._set_healthy(False)
        await self.session.close()

    async def _subscribe_events(self) -> None:
        by_notifier: dict[ua.NodeId, tuple[object, list]] = {}
        for route in self.link.events:
            type_node = await self.session.node(route.ua.form.topic)
            fields = [(await p.read_browse_name()).Name for p in await type_node.get_properties()]
            self._event_types[type_node.nodeid] = (route, fields)
            notifiers = await type_node.get_referenced_nodes(ua.ObjectIds.GeneratesEvent,
                                                             ua.BrowseDirection.Inverse)
            for notifier in notifiers:
                by_notifier.setdefault(notifier.nodeid, (notifier, []))[1].append(type_node)
        for notifier, types in by_notifier.values():
            await self._subscription.subscribe_events(notifier, types, queuesize=100)

    # -- OPC UA -> UNS (asyncua subscription handler, runs in the event loop) ---------------------------

    def datachange_notification(self, node, value, data) -> None:
        dv = data.monitored_item.Value
        good = dv.StatusCode is None or dv.StatusCode.is_good()
        self._set_healthy(good)
        route = self._points.get(node.nodeid)
        if not good or route is None:
            return
        uns = route.uns
        payload = {uns.key("Value", "v"): value, uns.key("Timestamp", "ts"): iso(dv.SourceTimestamp)}
        self.mqtt.publish(uns.form.topic, payload, qos=uns.form.qos, retain=uns.form.retain)
        self.stats["telemetry"] += 1

    def event_notification(self, event) -> None:
        fields = {k: v.Value for k, v in event.get_event_props_as_fields_dict().items()}
        entry = self._event_types.get(fields.get("EventType"))
        if entry is None:
            return
        route, names = entry
        payload = {"event": route.name, "device": fields.get("SourceName"),
                   "session": fields.get("Session"), "seq": fields.get("Seq"), "ts": iso(fields.get("Time"))}
        payload |= {name: fields.get(name) for name in names if name not in STANDARD_FIELDS}
        self.mqtt.publish(route.uns.form.topic, payload, qos=route.uns.form.qos, retain=route.uns.form.retain)
        self.stats["events"] += 1

    def status_change_notification(self, status) -> None:
        log.warning("subscription status of %s: %s", self.session.endpoint, status)

    async def _connection_lost(self, exc: Exception) -> None:
        log.warning("OPC UA connection to %s lost (%s); reconnecting", self.session.endpoint,
                    status_text(exc))
        self._set_healthy(False)

    def _set_healthy(self, healthy: bool) -> None:
        if healthy == self.healthy:
            return
        self.healthy = healthy
        for topic, route in self.commands.items():
            if healthy:
                self.mqtt.subscribe(topic, qos=route.uns.form.qos)
            else:
                self.mqtt.unsubscribe(topic)
        log.info("%s %s: command topics %s", self.session.endpoint,
                 "delivers good values" if healthy else "has no valid data",
                 "subscribed" if healthy else "unsubscribed")

    # -- UNS -> OPC UA -----------------------------------------------------------------------------

    async def handle_command(self, msg: Message) -> bool:
        route = self.commands.get(msg.topic)
        if route is None:
            return False
        uns = route.uns
        data = msg.json()
        corr = data.get(uns.key("CorrelationId", "corr")) if isinstance(data, dict) else None
        value_key = uns.key("Value", "v")
        if not isinstance(data, dict) or value_key not in data:
            self._ack(route, corr, False, f"payload must be a JSON object with '{value_key}'", None)
            return True
        value, start = data[value_key], time.perf_counter()
        try:
            await self.session.call(route.ua.form.topic, [value])
        except (ua.UaError, ValueError, OSError, TimeoutError) as exc:
            self._ack(route, corr, False, f"{self.session.endpoint}: {status_text(exc)}", None)
            return True
        self.stats["commands"] += 1
        self.stats["command_ms"] += (time.perf_counter() - start) * 1000.0
        self._ack(route, corr, True, "", value)
        return True

    def _ack(self, route: Route, corr, accepted: bool, reason: str, value) -> None:
        uns = route.uns
        if uns.ack is None:
            return
        ack = {uns.ack_key("CorrelationId", "corr"): corr, uns.ack_key("Accepted", "accepted"): accepted,
               uns.ack_key("Reason", "reason"): reason, uns.ack_key("Value", "v"): value,
               uns.ack_key("Timestamp", "ts"): now_iso()}
        self.mqtt.publish(uns.ack.topic, ack, qos=uns.ack.qos, retain=False)
