"""Order policy and publishing of the condition monitoring (fake historian, publisher and order opener)."""

from __future__ import annotations

import pytest

from maintenance.config import Config
from maintenance.history import Readings, query
from maintenance.monitor import Monitor
from maintenance.prognosis import Design, Sample
from maintenance.tasks import MaintenanceTask

TASK = MaintenanceTask("MI-PG85-01", "Replace gripper fingers", "Greiferfinger tauschen")


class _History:
    def __init__(self):
        self.readings_by_tag: dict[str, Readings] = {}

    def readings(self, component, session):
        return self.readings_by_tag.get(component.tag, Readings([]))


@pytest.fixture()
def setup():
    config = Config.load()
    history, published, opened = _History(), [], []

    def open_order(component, task, prognosis, summary):
        opened.append((component.tag, summary))
        return f"MO-2026-{len(opened):04d}"

    states = Monitor.states_for(config, {"GR01": TASK}, {"GR01": Design(2_500_000, 2_000_000)})
    monitor = Monitor(config, history, states, lambda *a: published.append(a), open_order)
    return monitor, history, published, opened


def _wear(n: int, rate: float) -> Readings:
    samples = [Sample(1000.0 + 12 * i, i, rate * i) for i in range(1, n + 1)]
    return Readings(samples, {"grip_cycles": n, "finger_wear": rate * n, "grip_force": 90.0})


def test_configuration_from_infra():
    component = Config.load().component("gr01")
    assert (component.device, component.indicator, component.cycles, component.limit) == \
        ("RB01", "finger_wear", "grip_cycles", 0.001)
    assert component.variables[:2] == ["grip_cycles", "finger_wear"]
    assert "gripper_fault" in component.variables
    assert component.alarm == 901 and component.reset_parameter == "gripper_maintenance_reset"
    sql = query(component, "S-1", 200)
    assert sql.startswith('SELECT "time", "grip_cycles", "finger_wear"') and 'FROM "rb01"' in sql
    assert "session = 'S-1'" in sql and sql.endswith("ORDER BY time DESC LIMIT 200")


def test_normal_wear_opens_no_order(setup):
    monitor, history, published, opened = setup
    history.readings_by_tag["GR01"] = _wear(30, 4e-10)
    state = monitor.evaluate("GR01")
    assert state.health == "Good" and not opened and monitor.alarm_word() == ""
    assert ("GR01", "health_state", "Good", 1360.0) in published


def test_accelerated_wear_opens_one_order_and_raises_the_advisory_alarm(setup):
    monitor, history, published, opened = setup
    history.readings_by_tag["GR01"] = _wear(8, 4.5e-5)
    state = monitor.evaluate("GR01")
    assert state.order == "MO-2026-0001" and state.health == "Warning"
    assert "health index 0.64" in opened[0][1] and "Replace gripper fingers (MI-PG85-01)" in opened[0][1]
    assert monitor.alarm_word() == "901" and ("", "active_alarms", "901", None) in published
    assert "maintenance order MO-2026-0001" in monitor.recommendation(state)["en"]
    monitor.evaluate("GR01")
    assert len(opened) == 1, "one open order per component"
    monitor.close_order("GR01", "MO-2026-0001")
    assert monitor.alarm_word() == "" and published[-1] == ("", "active_alarms", "", None)


def test_health_index_gate_and_rul_threshold(setup):
    monitor, history, _, opened = setup
    history.readings_by_tag["GR01"] = _wear(8, 1e-5)  # clear trend, RUL 92 grips = 0.31 h, but HI 0.92
    assert monitor.evaluate("GR01").health == "Good" and not opened, "above the health index gate"
    monitor.config.policy.update({"healthIndexGate": 0.95, "rulHoursThreshold": 0.25})
    assert monitor.evaluate("GR01").health == "Good" and not opened, "0.31 h above the threshold"
    monitor.config.policy.update({"rulHoursThreshold": 1.0})
    assert monitor.evaluate("GR01").health == "Warning" and len(opened) == 1


def test_device_failure_opens_an_order_at_once(setup):
    monitor, history, _, opened = setup
    history.readings_by_tag["GR01"] = Readings([Sample(1000.0, 3, 1e-5)], {})
    monitor.on_value("RB01", "gripper_fault", True)
    state = monitor.evaluate("GR01")
    assert state.health == "Alarm" and state.order == "MO-2026-0001" and state.faulted
