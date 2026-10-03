"""Integration checks against the running compose stack (`uv run pytest -m integration`): a UNS sample travels
MQTT -> historian -> InfluxDB, and the LinkedSegment query of a device AAS runs against InfluxDB."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from vf_common import ids
from vf_common.basyx import BasyxClient
from vf_common.historian import HistorianConfig, InfluxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

pytestmark = pytest.mark.integration
INFLUX = "http://localhost:8181"


@pytest.fixture(scope="module")
def influx():
    try:
        httpx.get(f"{INFLUX}/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("InfluxDB (compose stack) not running")
    return InfluxClient(INFLUX, HistorianConfig.load().database)


def test_uns_sample_reaches_influxdb(influx):
    """rb01/q1 is history-only (not mapped into the AAS), so the synthetic sample (year 2001) touches nothing
    but the historian."""
    mqtt = MqttClient(f"vf-historian-test-{time.time_ns()}")
    assert mqtt.start(), "MQTT broker not reachable"
    ts, value = "2001-01-01T00:00:00.123Z", round(time.time() % 1, 6)
    mqtt.publish(Uns.load().telemetry("RB01", "q1"), {"v": value, "ts": ts}, qos=1, retain=False)
    rows, deadline = [], time.monotonic() + 10
    while time.monotonic() < deadline and not rows:
        time.sleep(0.5)
        try:
            rows = influx.query(f"SELECT q1, session FROM rb01 WHERE time = '{ts}' AND q1 = {value}")
        except Exception:  # noqa: BLE001 - table not created yet
            rows = []
    mqtt.stop()
    assert rows and rows[0]["q1"] == pytest.approx(value) and rows[0]["session"]


def test_linked_segment_query_from_the_aas_runs(influx):
    """Copy-paste test of docs/interfaces/services.md: Endpoint + Query from the AAS, HTTP GET."""
    aas = BasyxClient("http://localhost:8091")
    try:
        segment = aas.get_value(ids.submodel_id("CV01", "TimeSeries", "1"), "Segments.Historian")
    except httpx.HTTPError:
        pytest.skip("AAS server not running")
    url = httpx.URL(segment["Endpoint"]).copy_merge_params({"q": segment["Query"]})  # keeps db and format
    response = httpx.get(url, timeout=10)
    assert response.status_code == 200, response.text[:300]
    rows = response.json()
    assert isinstance(rows, list)
    if rows:
        assert {"time", "power", "energy", "belt_speed"} <= set().union(*rows)
        assert rows == sorted(rows, key=lambda r: r["time"])
    print(json.dumps(rows[-3:]))
