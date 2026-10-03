"""Historian without servers: line-protocol encoding, batching/retry and UNS message handling."""

from __future__ import annotations

import json

from historian.batch import BatchWriter
from historian.lineprotocol import field_value, line, ts_millis
from historian.service import Historian, variable_types
from vf_common.historian import HistorianConfig, InfluxError
from vf_common.uns import Uns

ROOT = "vf/plant01/final-assembly/line01"


def test_field_values_follow_the_fmi_type():
    assert field_value("Float64", 0) == "0.0" and field_value("Float64", 12.5) == "12.5"
    assert field_value("Float64", float("nan")) is None and field_value("Float64", None) is None
    assert field_value("Int32", 3.0) == "3i" and field_value("Boolean", 1) == "true"
    assert field_value("Boolean", False) == "false"
    assert field_value("String", 'say "hi"\\') == '"say \\"hi\\"\\\\"'


def test_line_escaping_and_timestamp():
    text = line("cv 01", {"session": "S,1"}, {"belt speed": "0.25", "running": "true"}, 1759498614052)
    assert text == r"cv\ 01,session=S\,1 belt\ speed=0.25,running=true 1759498614052"
    assert ts_millis("2025-10-03T13:36:54.052Z") == 1759498614052


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_batching_merges_samples_of_one_tick_and_waits_for_the_interval():
    sent, clock = [], _Clock()
    w = BatchWriter(sent.append, interval_s=0.5, max_lines=3, clock=clock)
    w.add("cv01", "S1", "power", "12.0", 1000)
    w.add("cv01", "S1", "running", "true", 1000)   # same tick -> same line
    assert w.flush() == 1 and sent[0] == ["cv01,session=S1 power=12.0,running=true 1000"]
    w.add("cv01", "S1", "power", "13.0", 1100)
    clock.t = 0.2
    assert w.flush() == 0                           # interval not elapsed
    for ts in (1200, 1300):
        w.add("rb01", "S1", "q1", "0.1", ts)
    assert w.flush() == 3                           # max_lines reached -> sent early
    clock.t = 1.0
    assert w.flush() == 0 and w.stats.lines == 4 and w.stats.batches == 2


def test_transient_failures_are_retried_with_backoff_and_the_buffer_is_bounded():
    clock, attempts = _Clock(), []

    def send(lines):
        attempts.append(list(lines))
        if len(attempts) <= 2:
            raise InfluxError("connection refused", transient=True)

    w = BatchWriter(send, interval_s=0.5, max_lines=10, max_buffer=3, clock=clock)
    for ts in range(5):
        w.add("cv01", "S1", "power", "1.0", ts)
    assert w.pending == 3 and w.stats.dropped == 2   # oldest dropped
    assert w.flush() == 0 and w.stats.failures == 1  # retry in 1 s
    clock.t = 0.9
    assert w.flush() == 0 and len(attempts) == 1
    clock.t = 1.0
    assert w.flush() == 0 and w.stats.failures == 2  # retry in 2 s
    clock.t = 3.0
    assert w.flush() == 3 and w.pending == 0
    assert attempts[-1][0] == "cv01,session=S1 power=1.0 2"


def test_rejected_lines_are_dropped():
    def send(lines):
        raise InfluxError("HTTP 400 partial write", transient=False)

    w = BatchWriter(send, max_lines=10, clock=_Clock())
    w.add("cv01", "S1", "power", "1.0", 1)
    assert w.flush() == 1 and w.pending == 0 and w.stats.rejected == 1


class _Mqtt:
    def subscribe(self, topic, qos=1):
        pass


def test_historian_handles_session_and_telemetry():
    sent = []
    types = variable_types()
    assert types["rb01"]["q1"] == "Float64" and types["plc01"]["parts_total"] == "Int32"
    h = Historian(_Mqtt(), Uns.load(), types, BatchWriter(sent.append))
    h.handle(f"{ROOT}/session", json.dumps({"id": "S-1", "ts": "2026-10-03T10:00:00Z"}).encode())
    h.handle(f"{ROOT}/plc01/parts_total", json.dumps({"v": 7, "ts": "2026-10-03T10:00:01.500Z"}).encode())
    h.handle(f"{ROOT}/rb01/q1", json.dumps({"v": None, "ts": "2026-10-03T10:00:01.500Z"}).encode())
    h.handle(f"{ROOT}/sandbox/alert", b'{"v": 1, "ts": "2026-10-03T10:00:01.500Z"}')
    h.handle(f"{ROOT}/cv01/belt_speed", b"not json")
    h.writer.flush(force=True)
    assert sent == [["plc01,session=S-1 parts_total=7i 1791021601500"]]


def test_config_endpoint_and_query():
    config = HistorianConfig.load()
    assert config.endpoint() == "http://localhost:8181/api/v3/query_sql?db=vf&format=json"
    assert config.linked_query("KLTA01", ["full"]) == (
        'SELECT "time", "full" FROM "klta01" WHERE time >= now() - INTERVAL \'1 hour\' ORDER BY time')
