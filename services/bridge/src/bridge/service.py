"""AIMC bridge service: loads all mapping configurations from the AAS server, subscribes to the mapped UNS
topics and writes the values into the sink elements. Reloads when an AIMC or AID submodel changes (BaSyx MQTT
eventing) or periodically as a fallback."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict

from vf_common.basyx import BasyxClient
from vf_common.mqtt import MqttClient

from .aimc import AID_SEMANTIC_ID, AIMC_SEMANTIC_ID, Mapping, mappings, referenced_submodels
from .sinks import SinkWriter

log = logging.getLogger("bridge")
WATCHED = {AIMC_SEMANTIC_ID, AID_SEMANTIC_ID}


def load_all(aas: BasyxClient) -> list[Mapping]:
    """Mappings of every AIMC submodel on the server."""
    out: list[Mapping] = []
    for listed in aas.list_submodels(semantic_id=AIMC_SEMANTIC_ID):
        aimc = aas.get_submodel(listed["id"], blobs=True) or listed  # transformations are Blob values
        referenced = {sm_id: aas.get_submodel(sm_id) for sm_id in referenced_submodels(aimc)}
        try:
            out += mappings(aimc, {k: v for k, v in referenced.items() if v})
        except (KeyError, IndexError) as exc:
            log.warning("skipping AIMC %s: %s", aimc["id"], exc)
    return out


class Bridge:
    def __init__(self, aas: BasyxClient, mqtt: MqttClient, events_topic: str | None, reload_s: float = 300.0,
                 min_interval: float = 1.0):
        self.aas, self.mqtt, self.events_topic, self.reload_s = aas, mqtt, events_topic, reload_s
        self.writer = SinkWriter(aas.set_value, min_interval=min_interval)
        self.by_topic: dict[str, list[Mapping]] = {}
        self._reload_due = 0.0
        self._last_stats = time.monotonic()

    def reload(self) -> None:
        by_topic: dict[str, list[Mapping]] = defaultdict(list)
        for m in load_all(self.aas):
            by_topic[m.topic].append(m)
        for topic in set(by_topic) - set(self.by_topic):
            self.mqtt.subscribe(topic, qos=0)
        self.by_topic = dict(by_topic)
        self._reload_due = time.monotonic() + self.reload_s
        log.info("loaded %d mappings on %d topics", sum(map(len, by_topic.values())), len(by_topic))

    def handle(self, topic: str, payload: bytes, now: float) -> None:
        if self.events_topic and topic.startswith(self.events_topic.rstrip("#")):
            self._on_aas_event(payload)
            return
        targets = self.by_topic.get(topic)
        if not targets:
            return
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        for m in targets:
            if isinstance(data, dict) and m.value_key in data:
                value = m.convert(data[m.value_key])
                if value is not None:
                    self.writer.offer(m.sink_submodel, m.sink_path, value, now)

    def run(self) -> None:
        if self.events_topic:
            self.mqtt.subscribe(self.events_topic, qos=0)
        self.reload()
        while True:
            msg = self.mqtt.get(timeout=0.2)
            now = time.monotonic()
            if msg:
                self.handle(msg.topic, msg.payload, now)
            self.writer.flush(now)
            if now >= self._reload_due:
                self.reload()
            self._stats(now)

    def _on_aas_event(self, payload: bytes) -> None:
        """CloudEvent of BaSyx: reload (debounced) if a mapping-relevant submodel changed."""
        try:
            data = json.loads(payload).get("data") or {}
            semantic = data.get("semanticId", {}).get("keys", [{}])[0].get("value")
        except (ValueError, AttributeError, IndexError):
            return
        if semantic in WATCHED:
            self._reload_due = min(self._reload_due, time.monotonic() + 2.0)

    def _stats(self, now: float) -> None:
        if now - self._last_stats >= 60:
            log.info("writes=%d errors=%d", self.writer.writes, self.writer.errors)
            self._last_stats = now
