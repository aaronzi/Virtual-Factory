"""Keeps the gateway configuration in sync with the AAS: resolves it at start-up (retrying until the AAS
server answers), again on BaSyx change events for the submodels it was read from (LineControl, Control
Component Instance, AID) and every `reload_s` as a fallback (events are best effort, R1)."""

from __future__ import annotations

import json
import logging
import threading
import time

from vf_common.aid import AasSource
from vf_common.mqtt import Message

from .control import resolve
from .gateway import LineGateway

log = logging.getLogger("ops-gateway")


class ConfigWatcher:
    def __init__(self, source: AasSource, line_control_id: str, gateway: LineGateway,
                 events_topic: str | None, reload_s: float = 300.0, retry_s: float = 5.0,
                 debounce_s: float = 1.0):
        self.source, self.line_control_id, self.gateway = source, line_control_id, gateway
        self.events_prefix = events_topic.rstrip("#") if events_topic else None
        self.reload_s, self.retry_s, self.debounce_s = reload_s, retry_s, debounce_s
        self.due = 0.0
        self.reloads = 0
        self._wake = threading.Event()

    def on_message(self, msg: Message) -> None:
        """BaSyx CloudEvent: reload (debounced) if one of the configuration submodels changed."""
        if not self.events_prefix or not msg.topic.startswith(self.events_prefix):
            return
        try:
            submodel = (json.loads(msg.payload).get("data") or {}).get("submodelId")
        except (ValueError, AttributeError):
            return
        config = self.gateway.config
        if config is not None and submodel in config.sources:
            log.info("AAS change event for %s: reloading the configuration", submodel)
            self.due = min(self.due, time.monotonic() + self.debounce_s)
            self._wake.set()

    def reload(self) -> bool:
        try:
            config = resolve(self.source, self.line_control_id)
        except Exception as exc:  # noqa: BLE001 - server unreachable, preload running, model incomplete
            if self.gateway.config is None:
                log.error("cannot resolve the command endpoints from the AAS (%s): %s - operations are "
                          "rejected until this succeeds (no fallback to uns.json); retrying in %.0f s",
                          self.line_control_id, exc, self.retry_s)
            else:
                log.error("reload from the AAS failed, keeping the previous configuration: %s", exc)
            self.due = time.monotonic() + self.retry_s
            return False
        self.gateway.configure(config)
        self.reloads += 1
        self.due = time.monotonic() + self.reload_s
        return True

    def run(self) -> None:
        while True:
            wait = self.due - time.monotonic()
            if wait > 0:
                self._wake.wait(min(wait, 1.0))
                self._wake.clear()
                continue
            self.reload()
