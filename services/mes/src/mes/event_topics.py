"""Event topics of the MES, discovered from the AAS (ADR-0020): every event affordance of every Asset
Interfaces Description on the server (`InteractionMetadata.events.<name>.forms.href`). Topic -> event name
(the affordance idShort, e.g. part_sorted), which events.py maps to BPMN messages.

Reloaded (debounced) when BaSyx reports a change of an AID submodel and every `reload_s` as a fallback. If the
AAS is unreachable or describes no events, the previous topics are kept and the failure is logged as an error;
there is no fallback to the UNS registry. The session birth (`{root}/session`) is not an asset affordance and
stays in the UNS registry (see events.py)."""

from __future__ import annotations

import logging
import time

from vf_common.aid import AID_SEMANTIC_ID, AasSource, aid_submodels, events

log = logging.getLogger("mes.events")


def discover(aas: AasSource) -> dict[str, str]:
    """{topic: event name} of all AID event affordances on the server."""
    topics = {}
    for aid in aid_submodels(aas):
        for event in events(aid):
            if event.form.topic:
                topics[event.form.topic] = event.name
    return topics


class EventTopics:
    def __init__(self, aas: AasSource, mqtt, events_topic: str | None, reload_s: float = 300.0,
                 retry_s: float = 30.0, debounce_s: float = 2.0):
        self.aas, self.mqtt = aas, mqtt
        self.reload_s, self.retry_s, self.debounce_s = reload_s, retry_s, debounce_s
        self.events_prefix = events_topic.rstrip("#") if events_topic else None
        self.topics: dict[str, str] = {}
        self.due = 0.0
        if events_topic:
            mqtt.subscribe(events_topic, qos=0)

    def name(self, topic: str) -> str | None:
        return self.topics.get(topic)

    def is_aas_event(self, topic: str) -> bool:
        return bool(self.events_prefix) and topic.startswith(self.events_prefix)

    def on_aas_event(self, cloud_event: dict) -> None:
        data = cloud_event.get("data") or {}
        keys = (data.get("semanticId") or {}).get("keys") or [{}]
        if keys[0].get("value") == AID_SEMANTIC_ID:
            self.due = min(self.due, time.monotonic() + self.debounce_s)

    def tick(self, now: float) -> None:
        if now >= self.due:
            self.reload()

    def reload(self) -> bool:
        try:
            topics = discover(self.aas)
        except Exception as exc:  # noqa: BLE001 - server busy/unreachable: keep the current subscriptions
            log.error("event discovery from the AAS failed, keeping %d topics: %s", len(self.topics), exc)
            topics = {}
        if not topics:
            if not self.topics:
                log.error("no event affordances found in the AAS (AID events) - the MES receives no UNS "
                          "events; retrying in %.0f s (no fallback to uns.json)", self.retry_s)
            self.due = time.monotonic() + self.retry_s
            return False
        for topic in set(self.topics) - set(topics):
            self.mqtt.unsubscribe(topic)
        for topic in set(topics) - set(self.topics):
            self.mqtt.subscribe(topic, qos=1)
        if topics != self.topics:
            log.info("event topics from the AAS (AID events): %d\n  %s", len(topics),
                     "\n  ".join(f"{t} -> {n}" for t, n in sorted(topics.items())))
        self.topics, self.due = topics, time.monotonic() + self.reload_s
        return True
