"""Historian service: subscribes to the UNS telemetry of all devices and the session birth message and writes
every sample into InfluxDB 3 with the UNS timestamp (ADR-0019). Condition monitoring results of the
maintenance service ({root}/maintenance/{component}/{indicator}, ADR-0029) go into the table `maintenance`
with the tag `component`; their types are listed in uns.json (maintenance.indicators).

The devices and the FMI type of every output come from the asset data (`aas/data`, `device.modelDescription`),
the same source the provisioner uses for the AAS interfaces - unknown topics are ignored."""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path

from provisioner.build import REPO, load_assets
from provisioner.fmi import read_model_description
from vf_common.historian import HistorianConfig
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

from .batch import BatchWriter
from .lineprotocol import field_value, ts_millis

log = logging.getLogger("historian")


def variable_types(repo: Path = REPO) -> dict[str, dict[str, str]]:
    """{table (lower-case instance name): {FMI output: FMI type}} for every device of the asset data."""
    out: dict[str, dict[str, str]] = {}
    for spec in load_assets(repo / "aas" / "data"):
        device = spec.get("device")
        if device:
            md = read_model_description(repo / device["modelDescription"])
            table = HistorianConfig.table(device.get("instance", spec["tag"]))
            out[table] = {v.name: v.type for v in md.by_causality("output")}
    return out


PENDING_MAX = 20_000  # samples held while no session is known (oldest dropped first)


class Historian:
    def __init__(self, mqtt: MqttClient, uns: Uns, types: dict[str, dict[str, str]], writer: BatchWriter):
        self.mqtt, self.uns, self.types, self.writer = mqtt, uns, types, writer
        self.session: str | None = None
        # samples before the first session birth (e.g. the edge publishes the PLC's initial values a moment
        # before the factory announces its session): held and tagged once the session is known
        self._pending: deque[tuple] = deque(maxlen=PENDING_MAX)
        self._prefix = uns.root + "/"
        self._value_key = uns.config["payload"]["value_key"]
        self._ts_key = uns.config["payload"]["timestamp_key"]
        self._last_stats = time.monotonic()
        maintenance = uns.config.get("maintenance") or {}
        self.indicators: dict[str, str] = maintenance.get("indicators", {})
        self._maintenance_prefix = self._prefix + "maintenance/"

    def subscribe(self) -> None:
        self.mqtt.subscribe(self.uns.session_topic, qos=1)  # first: the retained birth precedes the telemetry
        self.mqtt.subscribe(self.uns.telemetry("+", "+"), qos=0)
        if self.indicators:
            self.mqtt.subscribe(self.uns.maintenance("+", "+"), qos=1)

    def handle(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        if topic == self.uns.session_topic:
            self.session = str(data.get("id") or self.session or "") or None
            log.info("session %s", self.session)
            self._flush_pending()
            return
        if topic.startswith(self._maintenance_prefix):
            self._maintenance(topic, data)
            return
        device, _, variable = topic.removeprefix(self._prefix).partition("/")
        fmi_type = self.types.get(device, {}).get(variable)
        value = field_value(fmi_type, data.get(self._value_key)) if fmi_type else None
        ts = data.get(self._ts_key)
        if value is None or not isinstance(ts, str):
            return
        try:
            ts_ms = ts_millis(ts)
        except ValueError:
            return
        self._add(device, variable, value, ts_ms)

    def _maintenance(self, topic: str, data: dict) -> None:
        component, _, indicator = topic.removeprefix(self._maintenance_prefix).partition("/")
        value_type = self.indicators.get(indicator)
        value = field_value(value_type, data.get(self._value_key)) if value_type and component else None
        ts = data.get(self._ts_key)
        if value is None or not isinstance(ts, str):
            return
        try:
            ts_ms = ts_millis(ts)
        except ValueError:
            return
        self._add("maintenance", indicator, value, ts_ms, {"component": component.upper()})

    def _add(self, table: str, field: str, value, ts_ms: int, tags: dict | None = None) -> None:
        if self.session is None:
            self._pending.append((table, field, value, ts_ms, tags))
        elif tags is None:
            self.writer.add(table, self.session, field, value, ts_ms)
        else:
            self.writer.add(table, self.session, field, value, ts_ms, tags)

    def _flush_pending(self) -> None:
        if self.session is None or not self._pending:
            return
        log.info("tagging %d samples from before the session birth with %s", len(self._pending), self.session)
        while self._pending:
            self._add(*self._pending.popleft())

    def run(self) -> None:
        self.subscribe()
        self.mqtt.start()
        while True:
            msg = self.mqtt.get(timeout=0.1)
            if msg:
                self.handle(msg.topic, msg.payload)
            self.writer.flush()
            self._log_stats()

    def _log_stats(self) -> None:
        now = time.monotonic()
        if now - self._last_stats >= 60:
            s = self.writer.stats
            log.info("samples=%d lines=%d batches=%d pending=%d dropped=%d rejected=%d failures=%d",
                     s.samples, s.lines, s.batches, self.writer.pending, s.dropped, s.rejected, s.failures)
            self._last_stats = now
