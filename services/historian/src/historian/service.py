"""Historian service: subscribes to the UNS telemetry of all devices and the session birth message and writes
every sample into InfluxDB 3 with the UNS timestamp (ADR-0019).

The devices and the FMI type of every output come from the asset data (`aas/data`, `device.modelDescription`),
the same source the provisioner uses for the AAS interfaces - unknown topics are ignored."""

from __future__ import annotations

import json
import logging
import time
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


class Historian:
    def __init__(self, mqtt: MqttClient, uns: Uns, types: dict[str, dict[str, str]], writer: BatchWriter):
        self.mqtt, self.uns, self.types, self.writer = mqtt, uns, types, writer
        self.session: str | None = None
        self._prefix = uns.root + "/"
        self._value_key = uns.config["payload"]["value_key"]
        self._ts_key = uns.config["payload"]["timestamp_key"]
        self._last_stats = time.monotonic()

    def subscribe(self) -> None:
        self.mqtt.subscribe(self.uns.session_topic, qos=1)  # first: the retained birth precedes the telemetry
        self.mqtt.subscribe(self.uns.telemetry("+", "+"), qos=0)

    def handle(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        if topic == self.uns.session_topic:
            self.session = str(data.get("id") or self.session or "")
            log.info("session %s", self.session)
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
        self.writer.add(device, self.session or "unknown", variable, value, ts_ms)

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
