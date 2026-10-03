"""MES logic without servers: workpiece AAS per stage (strictly validated), quality verdict, event mapping,
KPIs, order progress."""

from __future__ import annotations

import pytest

from mes import cell_data
from mes.events import EventRouter, message_for
from mes.handlers import OrderHandlers
from mes.kpi import KpiTracker
from mes.quality import Limits, evaluate
from mes.workpiece import WorkpieceSpec, load_blueprint, tag_of
from provisioner.build import BuildContext, load_assets
from vf_common.uns import Uns

SERIAL = "PC3280-2026-000777"
V = {"serial": SERIAL, "releasedAt": "2026-10-03T10:00:00.000Z", "leakRate": 0.41, "strokeTime": 0.318}
INSPECTED = {"inspectedAt": "2026-10-03T10:00:11.900Z", "deltaE": 3.4, "r": 0.77, "g": 0.09, "b": 0.11,
             "plcResult": 1}
SORTED = {"sortedAt": "2026-10-03T10:00:19.000Z", "container": 1, "slot": 4}


@pytest.fixture(scope="module")
def ctx():
    return BuildContext()


@pytest.fixture(scope="module")
def specs(ctx):
    thumb = {"path": "http://localhost:8091/shells/x/asset-information/thumbnail", "contentType": "image/png"}
    return WorkpieceSpec(load_blueprint(), ctx.positions, thumb)


@pytest.fixture(scope="module")
def type_spec(ctx):
    return load_assets(ctx.repo / "aas" / "data", {"PC3280_TYPE"})[0]


def _build(ctx, type_spec, spec):
    env = ctx.build([type_spec, spec], validate=True).environment
    shell = next(s for s in env["assetAdministrationShells"] if s["idShort"] == SERIAL.replace("-", "_"))
    names = {sm["idShort"] for sm in env["submodels"] if sm["id"] in
             {r["keys"][0]["value"] for r in shell["submodels"]}}
    return env, shell, names


@pytest.mark.parametrize("stage, extra, expected", [
    ("released", {}, {"Nameplate", "DppMetadata", "ExecutedProcesses", "AssetLocation"}),
    ("inspected", INSPECTED,
     {"QualityInspection", "MeasurementValue_CapColour", "MeasurementValue_LeakRate"}),
    ("packed", {**INSPECTED, **SORTED}, {"CarbonFootprint", "QualityInspection"}),
    ("lost", {}, {"ExecutedProcesses"}),
])
def test_workpiece_stages_build_valid_aas(ctx, specs, type_spec, stage, extra, expected):
    v = {**V, **extra}
    verdict = evaluate(v, Limits()) if "deltaE" in v else None
    spec = specs.build(v, stage, verdict, pcf=3.91 if stage == "packed" else None)
    assert spec["tag"] == tag_of(SERIAL)
    _, shell, names = _build(ctx, type_spec, spec)
    assert expected <= names
    assert shell["assetInformation"]["defaultThumbnail"]["path"].startswith("http://")


def test_packed_run_has_all_processes_with_real_times(ctx, specs, type_spec):
    v = {**V, **INSPECTED, **SORTED}
    spec = specs.build(v, "packed", evaluate(v, Limits()), pcf=3.91)
    run = next(s for s in spec["submodels"]
               if s["template"].startswith("ExecutedProcesses"))["values"]["Run"][0]
    ops = [p["_idShort"] for p in run["Process"]]
    assert ops == ["OP10", "OP20", "OP30", "OP40", "OP50", "OP60", "OP70", "OP75", "OP80", "OP90"]
    assert run["RunResult"] == "Completed"
    op70 = run["Process"][6]
    assert op70["ProcessEndTime"] == V["releasedAt"]
    assert run["Process"][-1]["ProcessEndTime"] == "2026-10-03T10:00:19.000Z"
    op50 = run["Process"][4]
    assert op50["ResourceParameters"]["+MeasuredLeakRate"]["value"] == 0.41


def test_verdict_combines_cell_tests_and_colour():
    v = {**V, **INSPECTED}
    assert evaluate(v, Limits()).passed
    leaking = evaluate({**v, "leakRate": 1.3}, Limits())
    assert not leaking.passed and leaking.colour_ok and leaking.planned_container == 2
    assert not evaluate({**v, "deltaE": 40}, Limits()).colour_ok


def test_lots_change_in_blocks():
    assert cell_data._lot("L2609-0412", 2) == "L2609-0414"
    assert cell_data._lot("DGP-260915-F", 1) == "DGP-260916-F"
    assert cell_data.serial_number(SERIAL) == 777


def test_event_messages():
    name, key, variables, all_ = message_for({"event": "part_released", "serial": SERIAL, "ts": "t",
                                              "leak_rate": 0.4, "stroke_time": 0.32, "cap_variant": 0})
    assert (name, key, all_) == ("PartReleased", SERIAL, False) and "capVariant" not in variables
    assert message_for({"event": "container_full", "device": "KLTB01"})[2] == {"container": 2}
    assert message_for({"event": "part_inspected", "serial": ""}) is None


class _Bpmn:
    def __init__(self, results):
        self.results, self.calls = list(results), []

    def correlate(self, message, key, variables, all_instances):
        self.calls.append(message)
        return self.results.pop(0)


def test_correlation_is_retried_until_the_instance_waits():
    bpmn = _Bpmn([False, False, True])
    router = EventRouter(bpmn, Uns.load(), on_session=None, on_exchange=None)
    router.handle("x", {"event": "part_sorted", "serial": SERIAL, "container": 1, "slot": 0, "ts": "t"},
                  now=0.0)
    router.retry(0.5)
    assert len(bpmn.calls) == 1 and router.pending
    router.retry(1.1)
    router.retry(2.2)
    assert bpmn.calls == ["PartSorted"] * 3 and not router.pending and router.correlated == 1


def test_kpi_time_accounting():
    kpi = KpiTracker()
    kpi.on_state(6, "2026-10-03T10:00:00Z")
    kpi.on_state(5, "2026-10-03T10:01:30Z")
    kpi.on_counter("parts_ok", 7)
    values = kpi.values("2026-10-03T10:01:40Z")
    assert values["ActualProductionTime"] == "PT1M30S" and values["ActualUnitDelayTime"] == "PT10S"
    assert values["GoodPart"] == "7"


class _Aas:
    def __init__(self, ok, nok):
        self.values = {"parts_ok": str(ok), "parts_nok": str(nok)}

    def get_value(self, sm, path):
        return self.values


def test_order_progress():
    v = {"goodAtStart": 10, "rejectsAtStart": 2, "checkGood": 10, "checkRejects": 2, "quantity": 5,
         "rejectRateLimit": "0.25"}
    progress = OrderHandlers(_Aas(14, 3)).order_progress(v)
    assert progress["produced"] == 4 and not progress["orderDone"] and not progress["rejectAlarm"]
    alarm = OrderHandlers(_Aas(17, 8)).order_progress(v)
    assert alarm["orderDone"] and alarm["rejectAlarm"] and alarm["checkGood"] == 17
