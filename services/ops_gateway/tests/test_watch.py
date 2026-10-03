"""Configuration life cycle: AAS unreachable at start (no uns.json fallback), reload on a BaSyx change event
of a configuration submodel (here: a changed OPC UA href of an AID action), unrelated events ignored."""

from __future__ import annotations

import copy
import json
import time

from ops_gateway.gateway import LineGateway
from ops_gateway.watch import ConfigWatcher
from provisioner.build import build
from vf_common import ids
from vf_common.aid import InMemoryAas, Resolver
from vf_common.mqtt import Message

LINE_CONTROL = ids.submodel_id("LINE01", "LineControl", "1")
AID = ids.submodel_id("PLC01", "AssetInterfacesDescription", "1")
EVENTS = "vf/basyx/submodelrepository/#"


class _Mqtt:
    def __init__(self):
        self.subscribed = set()

    def subscribe(self, topic, qos=1):
        self.subscribed.add(topic)

    def unsubscribe(self, topic):
        self.subscribed.discard(topic)


class _Down:
    def get_submodel(self, sm_id):
        raise ConnectionError("connection refused")


def _event(submodel_id: str) -> Message:
    body = {"type": "io.admin-shell.submodel.updated.v1", "data": {"submodelId": submodel_id}}
    return Message("vf/basyx/submodelrepository/submodel/updated", json.dumps(body).encode())


def test_unreachable_aas_keeps_the_gateway_unconfigured():
    gateway = LineGateway(_Mqtt())
    watcher = ConfigWatcher(_Down(), LINE_CONTROL, gateway, EVENTS, retry_s=5.0)
    assert not watcher.reload() and gateway.config is None
    assert watcher.due > time.monotonic() + 4  # retried later, nothing taken from uns.json


def test_change_event_reloads_changed_href():
    env = copy.deepcopy(build().environment)
    mqtt = _Mqtt()
    gateway = LineGateway(mqtt)
    watcher = ConfigWatcher(InMemoryAas(env), LINE_CONTROL, gateway, EVENTS, debounce_s=0.0)
    assert watcher.reload()
    assert gateway.config.endpoints["PackMLCommand"].form.topic.endswith(";s=PLC01.Commands.packml_command")
    assert all("/rb01/cmd-resp/" in t for t in mqtt.subscribed), \
        "OPC UA endpoints: nothing to subscribe on the broker (only the robot's MQTT acknowledgement)"

    watcher.on_message(_event(ids.submodel_id("QS01", "EnergyConsumption", "1")))
    assert watcher.due > time.monotonic() + 60  # unrelated submodel: no reload

    ref = {"keys": [{"type": "Submodel", "value": AID}] + [
        {"type": "SubmodelElementCollection", "value": v}
        for v in ("InterfaceOPCUA", "InteractionMetadata", "actions", "packml_command", "forms", "href")]}
    Resolver(InMemoryAas(env)).element(ref)["value"] = "?id=nsu=urn:test;s=Moved.packml_command"
    watcher.on_message(_event(AID))
    assert watcher.due <= time.monotonic()
    assert watcher.reload() and watcher.reloads == 2
    assert gateway.config.endpoints["PackMLCommand"].form.topic == "?id=nsu=urn:test;s=Moved.packml_command"
