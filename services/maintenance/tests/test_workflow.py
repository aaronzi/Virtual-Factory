"""MaintenanceOrder process: BPMN topics vs. handlers, the handlers with fake line / ERP / AAS, and the AAS
writer (records, observed reliability) against the environment built by the provisioner."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from maintenance.condition_aas import ConditionAas
from maintenance.config import Config
from maintenance.history import Readings
from maintenance.monitor import Monitor
from maintenance.prognosis import Design, Sample
from maintenance.tasks import from_submodel
from maintenance.workflow import MaintenanceHandlers
from provisioner.build import build
from vf_common.aas.templates import TemplateLibrary

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def env():
    return build().environment


class _Aas:
    """RegistryAas surface over an environment dict (resolver, repository and element access)."""

    def __init__(self, env):
        self.env, self.resolver = copy.deepcopy(env), self

    def submodel_of_asset(self, asset_id, id_short):
        tag = asset_id.rsplit("/", 1)[-1]
        return next(type("Sm", (), {"id": s["id"]}) for s in self.env["submodels"]
                    if f"/{tag}/{id_short}/" in s["id"])

    def submodel(self, sm_id):
        return sm_id

    def repository(self, endpoint):
        return self

    def get_submodel(self, sm_id):
        return next(s for s in self.env["submodels"] if s["id"] == sm_id)

    def put_submodel(self, submodel):
        self.env["submodels"] = [submodel if s["id"] == submodel["id"] else s for s in self.env["submodels"]]

    def _find(self, sm_id, path):
        elements = self.get_submodel(sm_id)["submodelElements"]
        for part in path.split("."):
            element = next(e for e in elements if e.get("idShort") == part)
            elements = element.get("value") if isinstance(element.get("value"), list) else []
        return element

    def get_element(self, sm_id, path):
        return copy.deepcopy(self._find(sm_id, path))

    def put_element(self, sm_id, path, element):
        self._find(sm_id, path).update(copy.deepcopy(element))

    def set_value(self, sm_id, path, value):
        self._find(sm_id, path)["value"] = str(value)

    def get_value(self, sm_id, path=None):
        def value(e):
            v = e.get("value")
            return {c["idShort"]: value(c) for c in v} if e["modelType"] == "SubmodelElementCollection" else v
        return {e["idShort"]: value(e) for e in self.get_submodel(sm_id)["submodelElements"]}


class _Line:
    def __init__(self, monitor):
        self.calls, self.monitor = [], monitor

    def invoke(self, operation, **inputs):
        self.calls.append((operation, inputs))
        if "gripper_maintenance_reset" in inputs.get("Parameters", ""):
            self.monitor.on_value("RB01", "grip_cycles", 0)  # the device confirms on the UNS
        return {"Accepted": "true"}


class _Erp:
    def __init__(self):
        self.windows, self.state = {}, "Requested"

    def request(self, order, start, reason):
        self.windows[order] = start
        return {"ID": "MW-0001"}

    def get(self, window_id):
        return {"State": self.state, "InterruptedOrder": None}

    def complete(self, window_id):
        self.state = "Completed"


def test_bpmn_topics_are_the_handlers_topics():
    xml = (REPO / "bpmn" / "maintenance_order.bpmn").read_text()
    topics = set(re.findall(r'operaton:topic="([^"]+)"', xml))
    assert topics == set(MaintenanceHandlers(None, None, None, None).topics())
    assert 'operaton:candidateGroups="maintenance"' in xml and "${lineFree}" in xml


def test_task_and_design_from_the_component_aas(env):
    aas = ConditionAas(_Aas(env), TemplateLibrary(REPO / "aas" / "templates"))
    task = aas.task("GR01", "FingerChange")
    assert (task.maintenance_id, task.name_en, task.working_time) == ("MI-PG85-01", "Replace gripper fingers",
                                                                       "20 minutes")
    assert len(task.steps) == 4 and task.steps[0].startswith("10 Secure the robot cell:")
    assert task.spare_parts[0].startswith("FS-PG85-V50") and "Spare parts: FS-PG85-V50" in task.instructions()
    assert aas.design("GR01", "FingerSet") == Design(2_500_000, 2_000_000)
    assert from_submodel({"submodelElements": []}, "FingerChange") is None


def test_order_handlers_and_record_in_the_aas(env):
    fake = _Aas(env)
    recorder = ConditionAas(fake, TemplateLibrary(REPO / "aas" / "templates"))
    config = Config.load()
    monitor = Monitor(config, None, Monitor.states_for(config, {}, {}), lambda *a: None, None)
    monitor.states["GR01"].order = "MO-2026-0001"
    monitor.on_value("RB01", "grip_cycles", 17)
    line, erp = _Line(monitor), _Erp()
    h = MaintenanceHandlers(monitor, line, erp, recorder, verify_timeout_s=0.5)
    v = {"_businessKey": "MO-2026-0001", "component": "GR01", "taskName": "Replace gripper fingers",
         "immediate": False, "resetParameter": "gripper_maintenance_reset", "maintenanceId": "MI-PG85-01",
         "healthIndexAtOpen": 0.64, "partsReplaced": True, "technician": "T. Tech", "findings": "pads worn"}
    v |= h.reserve(v)
    assert erp.windows == {"MO-2026-0001": "OrderBoundary"} and v["windowId"] == "MW-0001"
    assert h.check_line(v)["lineFree"] is False
    erp.state = "Active"
    v |= h.check_line(v) | h.line_stop(v)
    v |= h.device_reset(v)
    assert (v["lineFree"], v["deviceReset"], v["cyclesAtMaintenance"]) == (True, True, 17)
    v |= h.handback(v)
    v |= h.record(v)
    assert [c[0] for c in line.calls] == ["ExecuteSkill", "ExecuteSkill", "SetUnitMode"]
    assert line.calls[1][1]["Parameters"] == '{"gripper_maintenance_reset": true}'
    assert erp.state == "Completed" and monitor.states["GR01"].order == ""
    sm_id = recorder.submodel_id("GR01", "ConditionMonitoring")
    [record] = fake.get_element(sm_id, "MaintenanceRecords")["value"]
    values = {p["idShort"]: p["value"] for p in record["value"]}
    assert values["MaintenanceOrderId"] == "MO-2026-0001" and values["CyclesAtMaintenance"] == "17"
    assert values["Technician"] == "T. Tech" and values["PartsReplaced"] == "true"
    reliability = fake.get_value(recorder.submodel_id("GR01", "Reliability"))
    assert reliability["NumberOfReliabilitySets"] == "3"
    assert reliability["CharacteristicsFingerSetObserved"]["B10"] == "9"  # Weibull(3) from a 17-grip life
    assert reliability["ConditionsFingerSetObserved"]["UsefulLifeInNumberOfOperations"] == "17.0"


def test_condition_values_are_written_only_when_changed(env):
    fake = _Aas(env)
    recorder = ConditionAas(fake, TemplateLibrary(REPO / "aas" / "templates"))
    config = Config.load()
    states = Monitor.states_for(config, {}, {"GR01": Design(2_500_000, 2_000_000)})
    monitor = Monitor(config, None, states, lambda *a: None, lambda *a: "MO-1")
    samples = [Sample(1000.0 + 12 * i, i, 4.5e-5 * i) for i in range(1, 9)]
    monitor.apply(states["GR01"], Readings(samples, {"grip_force": 88.5}), now=1100.0)
    writes = []
    fake.set_value = lambda sm, path, value, f=fake.set_value: (writes.append(path), f(sm, path, value))
    recorder.update(states["GR01"], monitor.recommendation(states["GR01"]), 8.0)
    values = fake.get_value(recorder.submodel_id("GR01", "ConditionMonitoring"))
    assert values["HealthState"] == "Warning" and values["OpenMaintenanceOrder"] == "MO-1"
    assert values["RemainingUsefulLife"]["Method"] == "TrendFit"
    assert values["Symptoms"]["GripForce"] == "88.5" and values["HealthIndex"] == "0.64"
    count = len(writes)
    recorder.update(states["GR01"], monitor.recommendation(states["GR01"]), 8.0)
    assert len(writes) == count, "unchanged values are not written again"
