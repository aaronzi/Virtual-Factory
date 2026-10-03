"""AIMC interpretation against the generated AAS (no server needed) and the sink write policy."""

from __future__ import annotations

import json

import pytest

from bridge.aimc import AIMC_SEMANTIC_ID, mappings, referenced_submodels
from bridge.service import Bridge
from bridge.sinks import SinkWriter
from provisioner.build import build

ROOT = "vf/plant01/final-assembly/line01"


@pytest.fixture(scope="module")
def cv01():
    env = build(only={"CV01", "LB01", "LB_TYPE"}).environment
    by_id = {sm["id"]: sm for sm in env["submodels"]}
    aimcs = [sm for sm in env["submodels"] if sm["semanticId"]["keys"][0]["value"] == AIMC_SEMANTIC_ID]
    return {aimc["id"].split("/")[5]: mappings(aimc, {i: by_id[i] for i in referenced_submodels(aimc)})
            for aimc in aimcs}


def test_mappings_point_from_uns_topics_to_typed_sinks(cv01):
    fault = next(m for m in cv01["CV01"] if m.source_id == "fault")
    assert fault.topic == f"{ROOT}/cv01/fault" and fault.value_key == "v"
    assert fault.sink_path == "ProcessValues.fault" and fault.sink_type == "xs:boolean"
    assert fault.sink_submodel.endswith("/CV01/OperationalData/1")
    power = next(m for m in cv01["CV01"] if m.source_id == "power")
    assert power.sink_path == "ActualPower" and power.sink_type == "xs:double"
    assert power.sink_submodel.endswith("/CV01/EnergyConsumption/1")
    # slim AAS (ADR-0019): continuous signals are history-only - not mapped into the AAS
    assert not any(m.source_id in ("belt_speed", "belt_position") for m in cv01["CV01"])


def test_lookup_transformation_and_conversion(cv01):
    state = next(m for m in cv01["LB01"] if m.sink_path == "OperatingState")
    assert state.convert(True) == "ObjectDetected" and state.convert(False) == "BeamClear"
    count = next(m for m in cv01["LB01"] if m.source_id == "switch_count")
    assert count.convert(3.0) == 3 and isinstance(count.convert(3.0), int)


def test_sink_writer_policy():
    written = []
    w = SinkWriter(lambda sm, path, v: written.append((path, v)), min_interval=1.0)
    w.offer("sm", "flag", True, now=0.0)
    w.offer("sm", "flag", True, now=0.1)       # unchanged: no write
    w.offer("sm", "speed", 0.25, now=0.0)
    w.offer("sm", "speed", 0.26, now=0.5)      # too early: pending
    w.offer("sm", "speed", 0.2501, now=0.6)    # replaces pending ... inside deadband of 0.25 -> dropped
    w.offer("sm", "speed", 0.27, now=0.7)
    w.flush(now=0.9)
    assert written == [("flag", True), ("speed", 0.25)]
    w.flush(now=1.1)
    assert written[-1] == ("speed", 0.27)


class _Aas:
    def __init__(self):
        self.calls = []

    def set_value(self, sm, path, value):
        self.calls.append((sm, path, value))


class _Mqtt:
    def subscribe(self, topic, qos=1):
        pass


def test_bridge_routes_messages(cv01):
    aas = _Aas()
    bridge = Bridge(aas, _Mqtt(), events_topic="vf/basyx/#")
    bridge.by_topic = {m.topic: [m] for m in cv01["CV01"] if m.source_id == "running"}
    bridge.handle(f"{ROOT}/cv01/running", json.dumps({"v": True, "ts": "x"}).encode(), now=0.0)
    assert [c[1:] for c in aas.calls] == [("ProcessValues.running", True)]
    bridge.handle(f"{ROOT}/cv01/running", b"not json", now=1.0)
    assert len(aas.calls) == 1
