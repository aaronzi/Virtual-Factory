"""Event topics discovered from the AID event affordances of the built AAS (no server, no uns.json for
events): subscription, routing by topic, reload on an AID change event."""

from __future__ import annotations

import copy

import pytest

from mes.event_topics import EventTopics, discover
from mes.events import EventRouter
from provisioner.build import build
from vf_common.aid import AID_SEMANTIC_ID, InMemoryAas, child
from vf_common.uns import Uns

ROOT = "vf/plant01/final-assembly/line01/"
EVENTS = "vf/basyx/submodelrepository/#"


class _Mqtt:
    def __init__(self):
        self.subscribed = set()

    def subscribe(self, topic, qos=1):
        self.subscribed.add(topic)

    def unsubscribe(self, topic):
        self.subscribed.discard(topic)


class _Bpmn:
    def __init__(self):
        self.calls = []

    def correlate(self, message, key, variables, all_instances):
        self.calls.append((message, key, variables))
        return True


@pytest.fixture(scope="module")
def env():
    return build().environment


def test_discover_all_aid_events(env):
    topics = discover(InMemoryAas(env))
    assert topics[ROOT + "ac01/event/part_released"] == "part_released"
    assert topics[ROOT + "plc01/event/part_sorted"] == "part_sorted"
    assert {n for t, n in topics.items() if "/klt" in t} == {"container_full", "container_exchanged"}
    assert len(topics) == 7


def test_router_uses_discovered_topics_and_reloads_on_aid_change(env):
    env = copy.deepcopy(env)
    mqtt, bpmn, exchanged = _Mqtt(), _Bpmn(), []
    topics = EventTopics(InMemoryAas(env), mqtt, EVENTS, debounce_s=0.0)
    assert topics.reload() and EVENTS in mqtt.subscribed
    assert ROOT + "plc01/event/part_sorted" in mqtt.subscribed
    router = EventRouter(bpmn, Uns.load(), None, lambda tag, n: exchanged.append(tag), topics=topics)
    sorted_event = {"event": "part_sorted", "serial": "S1", "container": 1, "slot": 2, "ts": "t"}
    router.handle(ROOT + "plc01/event/part_sorted", sorted_event, now=0.0)
    router.handle("vf/other/event/part_sorted", sorted_event, now=0.0)  # not described in the AAS: ignored
    assert [c[0] for c in bpmn.calls] == ["PartSorted"]
    router.handle(ROOT + "klta01/event/container_exchanged", {"device": "KLTA01", "exchange_count": 1}, 0.0)
    assert exchanged == ["KLTA01"]

    aid = next(s for s in env["submodels"] if s["id"].endswith("/PLC01/AssetInterfacesDescription/1"))
    form = _event_form(aid, "part_sorted")
    child(form["value"], "href")["value"] = "/vf/test/plc01/event/part_sorted"
    change = {"data": {"submodelId": aid["id"], "semanticId": {"keys": [{"value": AID_SEMANTIC_ID}]}}}
    router.handle("vf/basyx/submodelrepository/submodel/updated", change, 0.0)
    router.retry(topics.due)
    assert "vf/test/plc01/event/part_sorted" in mqtt.subscribed
    assert ROOT + "plc01/event/part_sorted" not in mqtt.subscribed
    router.handle("vf/test/plc01/event/part_sorted", sorted_event, now=1.0)
    assert [c[0] for c in bpmn.calls] == ["PartSorted", "PartSorted"]


def test_no_events_in_the_aas_keeps_subscriptions_empty():
    topics = EventTopics(InMemoryAas({"submodels": [], "assetAdministrationShells": []}), _Mqtt(), None)
    assert not topics.reload() and topics.topics == {}


def _event_form(aid: dict, name: str) -> dict:
    meta = child(aid["submodelElements"][0]["value"], "InteractionMetadata")
    return child(child(child(meta["value"], "events")["value"], name)["value"], "forms")
