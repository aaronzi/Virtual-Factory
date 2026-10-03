"""MQTT client for the services (paho-mqtt 2): subscriptions survive reconnects, messages are queued and
handled on the service's own thread (no blocking REST calls inside the network loop)."""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as paho

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    topic: str
    payload: bytes
    retain: bool = False

    def json(self) -> Any:
        try:
            return json.loads(self.payload)
        except (ValueError, UnicodeDecodeError):
            return None


class MqttClient:
    def __init__(self, client_id: str, host: str = "localhost", port: int = 1883):
        self.host, self.port = host, port
        self.messages: queue.Queue[Message] = queue.Queue()
        self.connected = threading.Event()
        self._subscriptions: dict[str, int] = {}
        self._client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
        self._client.reconnect_delay_set(1, 30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def start(self, wait_s: float = 10.0) -> bool:
        """Connects in the background (retrying until the broker is reachable); True if connected within
        wait_s."""
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()
        return self.connected.wait(wait_s)

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self._subscriptions[topic] = qos
        if self.connected.is_set():
            self._client.subscribe(topic, qos)

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> None:
        data = payload if isinstance(payload, (bytes, str)) else json.dumps(payload, separators=(",", ":"))
        self._client.publish(topic, data, qos=qos, retain=retain)

    def get(self, timeout: float | None = None) -> Message | None:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("MQTT connect to %s:%s refused: %s", self.host, self.port, reason_code)
            return
        for topic, qos in self._subscriptions.items():
            client.subscribe(topic, qos)
        self.connected.set()
        log.info("MQTT connected to %s:%s", self.host, self.port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected.clear()
        log.warning("MQTT disconnected (%s), reconnecting", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        self.messages.put(Message(msg.topic, msg.payload, bool(msg.retain)))
