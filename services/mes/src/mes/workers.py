"""External-task worker loop: long-polls a set of topics and runs the registered handler for each task.

A handler receives the task's process variables (plus `_businessKey`, `_activityId`) and returns variables to
set on completion. Exceptions become incidents after the retries are used up (visible in Operaton Cockpit)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .bpmn import BpmnClient, from_variables

log = logging.getLogger("mes.worker")
Handler = Callable[[dict[str, Any]], dict[str, Any] | None]


class Worker(threading.Thread):
    def __init__(self, bpmn: BpmnClient, name: str, handlers: dict[str, Handler], retries: int = 3):
        super().__init__(daemon=True, name=name)
        self.bpmn, self.handlers, self.retries = bpmn, handlers, retries
        self.worker_id = f"vf-mes-{name}"
        self.completed = 0

    def run(self) -> None:
        while True:
            try:
                tasks = self.bpmn.fetch_and_lock(self.worker_id, list(self.handlers))
            except Exception as exc:  # noqa: BLE001 - engine restarting; keep polling
                log.warning("%s: fetchAndLock failed: %s", self.name, exc)
                time.sleep(5)
                continue
            for task in tasks:
                self.execute(task)

    def execute(self, task: dict) -> None:
        variables = from_variables(task.get("variables"))
        variables["_businessKey"] = task.get("businessKey")
        variables["_activityId"] = task.get("activityId")
        try:
            result = self.handlers[task["topicName"]](variables) or {}
            self.bpmn.complete(task["id"], self.worker_id, result)
            self.completed += 1
        except Exception as exc:  # noqa: BLE001 - reported to the engine as failure / incident
            retries = task.get("retries")
            remaining = (self.retries if retries is None else retries) - 1
            log.warning("%s %s (%s) failed: %s", task["topicName"], task.get("businessKey"), remaining, exc)
            try:
                self.bpmn.failure(task["id"], self.worker_id, str(exc), max(remaining, 0), 5000)
            except Exception as report_exc:  # noqa: BLE001
                log.error("could not report failure: %s", report_exc)
