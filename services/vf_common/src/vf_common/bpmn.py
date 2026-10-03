"""Thin client for the Operaton (Camunda 7 compatible) engine REST API: external tasks, message correlation,
process instances and deployments. Shared by the services (MES and sustainability workers, ERP order
release)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .auth import bpmn_auth


class BpmnError(RuntimeError):
    pass


def to_variables(values: dict[str, Any]) -> dict[str, dict]:
    """Python values -> typed engine variables."""
    out = {}
    for name, value in values.items():
        if isinstance(value, bool):
            out[name] = {"value": value, "type": "Boolean"}
        elif isinstance(value, int):
            out[name] = {"value": value, "type": "Long"}
        elif isinstance(value, float):
            out[name] = {"value": value, "type": "Double"}
        elif isinstance(value, (dict, list)):
            out[name] = {"value": json.dumps(value), "type": "Json"}
        else:
            out[name] = {"value": None if value is None else str(value), "type": "String"}
    return out


def from_variables(variables: dict[str, dict] | None) -> dict[str, Any]:
    out = {}
    for name, var in (variables or {}).items():
        value = var.get("value")
        if var.get("type") == "Json" and isinstance(value, str):
            value = json.loads(value)
        out[name] = value
    return out


class BpmnClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        """Secure profile: basic auth of the service's engine user (VF_BPMN_USER / VF_BPMN_PASSWORD)."""
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, auth=bpmn_auth())

    def engine_ready(self) -> bool:
        try:
            return self.http.get("/engine").status_code == 200
        except httpx.HTTPError:
            return False

    def fetch_and_lock(self, worker_id: str, topics: list[str], max_tasks: int = 5, lock_ms: int = 60000,
                       long_poll_ms: int = 10000) -> list[dict]:
        body = {"workerId": worker_id, "maxTasks": max_tasks, "asyncResponseTimeout": long_poll_ms,
                "topics": [{"topicName": t, "lockDuration": lock_ms} for t in topics]}
        response = self.http.post("/external-task/fetchAndLock", json=body, timeout=long_poll_ms / 1000 + 10)
        self._check(response, "fetchAndLock")
        return response.json()

    def complete(self, task_id: str, worker_id: str, variables: dict[str, Any] | None = None) -> None:
        body = {"workerId": worker_id, "variables": to_variables(variables or {})}
        self._check(self.http.post(f"/external-task/{task_id}/complete", json=body), "complete")

    def failure(self, task_id: str, worker_id: str, message: str, retries: int,
                retry_timeout_ms: int) -> None:
        body = {"workerId": worker_id, "errorMessage": message[:600], "retries": retries,
                "retryTimeout": retry_timeout_ms}
        self._check(self.http.post(f"/external-task/{task_id}/failure", json=body), "failure")

    def correlate(self, message: str, business_key: str | None = None,
                  variables: dict[str, Any] | None = None, all_instances: bool = False) -> bool:
        """True if the message was correlated (started or continued an instance),
        False if nothing waits for it."""
        body: dict[str, Any] = {"messageName": message, "all": all_instances,
                                "processVariables": to_variables(variables or {})}
        if business_key:
            body["businessKey"] = business_key
        response = self.http.post("/message", json=body)
        if response.status_code == 400 and "correlat" in response.text.lower():
            return False
        self._check(response, f"correlate {message}")
        return True

    def start(self, process_key: str, business_key: str | None = None, variables: dict | None = None) -> str:
        body = {"variables": to_variables(variables or {}),
                **({"businessKey": business_key} if business_key else {})}
        response = self.http.post(f"/process-definition/key/{process_key}/start", json=body)
        self._check(response, f"start {process_key}")
        return response.json()["id"]

    def delete_instances(self, process_key: str, reason: str) -> None:
        body = {"processInstanceQuery": {"processDefinitionKey": process_key}, "deleteReason": reason,
                "skipCustomListeners": True, "skipSubprocesses": True}
        response = self.http.post("/process-instance/delete", json=body)
        if response.status_code != 400:  # 400: no instances
            self._check(response, "delete instances")

    def count_instances(self, process_key: str, business_key: str | None = None) -> int:
        params = {"processDefinitionKey": process_key}
        if business_key:
            params["businessKey"] = business_key
        response = self.http.get("/process-instance/count", params=params)
        self._check(response, "count")
        return response.json()["count"]

    def instances(self, process_key: str) -> list[dict]:
        """Running instances of a process (id, businessKey, ...)."""
        response = self.http.get("/process-instance", params={"processDefinitionKey": process_key})
        self._check(response, "instances")
        return response.json()

    def variables(self, instance_id: str) -> dict[str, Any]:
        response = self.http.get(f"/process-instance/{instance_id}/variables")
        self._check(response, "variables")
        return from_variables(response.json())

    def deploy(self, name: str, files: list[Path]) -> None:
        data = {"deployment-name": name, "deploy-changed-only": "true", "enable-duplicate-filtering": "true"}
        # one field per resource
        upload = [(f.name, (f.name, f.read_bytes(), "application/xml")) for f in files]
        self._check(self.http.post("/deployment/create", data=data, files=upload), "deploy")

    @staticmethod
    def _check(response: httpx.Response, what: str) -> None:
        if response.status_code >= 300:
            raise BpmnError(f"{what}: HTTP {response.status_code} {response.text[:300]}")
