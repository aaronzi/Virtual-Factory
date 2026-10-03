#!/usr/bin/env python3
"""Readiness gates and the skip check of the integration run (tools/ci_integration.sh, docs/development.md).

    uv run tools/ci_integration.py stack   [--timeout S]   compose services up/healthy, one-shots done, AAS
                                                           and supplier preload imported, services ready
    uv run tools/ci_integration.py shipped [--timeout S]   a packed good part's passport is Active (session 1)
    uv run tools/ci_integration.py factory [--timeout S]   the linked factory produces: every precondition the
                                                           integration tests would otherwise skip on
    uv run tools/ci_integration.py skips <junit.xml> [--allow <substring>]...
                                                           exit 1 if a test was skipped (or none ran)

Gates poll until all checks pass (readiness is the only place that retries); on timeout they print the
failing checks and exit 1. VF_CI_COMPOSE: compose command line (default: base + CI override file).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import httpx
from asyncua import Client, ua

from vf_common.basyx import BasyxClient
from vf_common.historian import HistorianConfig, InfluxClient
from vf_common.mqtt import MqttClient
from vf_common.uns import Uns

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = os.environ.get("VF_CI_COMPOSE", "docker compose -f infra/docker-compose.yml "
                         "-f infra/docker-compose.ci.yml")
ONE_SHOTS = {"provisioner", "supplier-provisioner", "basyx-config", "supplier-config"}
AAS, SUPPLIER, DPP = "http://localhost:8091", "http://localhost:8191", "http://localhost:8093"
BPMN = "http://localhost:8092/engine-rest"
HEALTH = {"ops-gateway": "http://localhost:8095/health", "resolver": "http://localhost:8096/health",
          "sustainability": "http://localhost:8097/health", "erp": "http://localhost:8098/health",
          "alarms": "http://localhost:8099/health", "maintenance": "http://localhost:8094/health",
          "supplier": "http://localhost:8190/health", "dpp-api": f"{DPP}/health",
          "influxdb3": "http://localhost:8181/health", "grafana": "http://localhost:3002/api/health"}
DPP_METADATA = "https://admin-shell.io/idta/cds/dppMetadata/1"
Check = Callable[[], str | None]  # None = passed, otherwise what is still missing


def _get(url: str, **params):
    response = httpx.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def gate(checks: dict[str, Check], timeout_s: float, step_s: float = 5.0) -> bool:
    started = time.monotonic()
    deadline, last_report = started + timeout_s, started
    pending: dict[str, str] = {name: "not checked" for name in checks}
    while True:
        for name in list(pending):
            try:
                problem = checks[name]()
            except Exception as exc:  # noqa: BLE001 - services still starting: report and retry
                problem = f"{type(exc).__name__}: {exc}"[:200]
            if problem is None:
                print(f"  ok  {name} ({time.monotonic() - started:.0f} s)", flush=True)
                del pending[name]
            else:
                pending[name] = problem
        if not pending:
            return True
        if time.monotonic() > deadline:
            for name, problem in pending.items():
                print(f"  FAILED  {name}: {problem}", flush=True)
            return False
        if time.monotonic() - last_report > 30:
            last_report = time.monotonic()
            print(f"  waiting for: {', '.join(pending)}", flush=True)
        time.sleep(step_s)


# -- stack ------------------------------------------------------------------------------------------------

def _compose_ps() -> list[dict]:
    out = subprocess.run([*shlex.split(COMPOSE), "ps", "-a", "--format", "json"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.strip()
    if out.startswith("["):  # older compose versions print one array, newer ones one object per line
        return json.loads(out)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def check_containers() -> str | None:
    problems = []
    for c in _compose_ps():
        name, state, health = c["Service"], c["State"], c.get("Health", "")
        if name in ONE_SHOTS:
            if state != "exited" or int(c.get("ExitCode", 0)) != 0:
                problems.append(f"{name} {state} (exit {c.get('ExitCode')})")
        elif state != "running" or health not in ("", "healthy"):
            problems.append(f"{name} {state} {health}".strip())
    if any("exit" in p and "(exit 0)" not in p for p in problems):
        raise SystemExit(f"one-shot container failed: {problems}")
    return ", ".join(problems) or None


def _preload_check(url: str, folder: str) -> Check:
    expected = len(list((ROOT / "infra/basyx" / folder).glob("*.aasx")))

    def check() -> str | None:
        shells = [s for s in _get(f"{url}/shells", limit=2000)["result"] if "/aas/WP_" not in s["id"]]
        return None if expected and len(shells) >= expected else f"{len(shells)} of >= {expected} shells"
    return check


def check_bpmn() -> str | None:
    """The MES deploys the BPMN models at start; the ERP releases the standing order through them."""
    keys = {d["key"] for d in _get(f"{BPMN}/process-definition", latestVersion="true")}
    missing = {"ProductionOrder", "MaintenanceOrder"} - keys
    return f"not deployed: {sorted(missing)}" if missing else None


def check_ops_gateway() -> str | None:
    health = _get(HEALTH["ops-gateway"])
    endpoint = health.get("endpoints", {}).get("PackMLCommand", {})
    return None if health["status"] == "ok" and endpoint.get("protocol") == "opcua" else str(health)[:200]


def _health(url: str) -> Check:
    return lambda: None if httpx.get(url, timeout=5).status_code == 200 else f"{url} not 200"


def stack_checks() -> dict[str, Check]:
    checks: dict[str, Check] = {"containers": check_containers,
                                "AAS preload": _preload_check(AAS, "preload"),
                                "supplier preload": _preload_check(SUPPLIER, "preload-supplier"),
                                "BPMN models deployed": check_bpmn,
                                "ops gateway endpoints": check_ops_gateway}
    checks.update({f"{name} health": _health(url) for name, url in HEALTH.items()})
    return checks


# -- factory ----------------------------------------------------------------------------------------------

def _passports() -> list[dict]:
    """DPP metadata of the workpieces: [{'id', 'dppStatus', 'lastUpdate'}]."""
    sms = BasyxClient(AAS).list_submodels(semantic_id=DPP_METADATA, semantic_key_type="Submodel")
    return [{"id": sm["id"], **{e["idShort"]: e.get("value") for e in sm.get("submodelElements", [])}}
            for sm in sms if "/sm/WP_" in sm["id"]]


def check_shipped() -> str | None:
    active = [p for p in _passports() if p.get("dppStatus") == "Active"]
    return None if active else "no Active passport yet"


def _retained(topic: str) -> dict:
    client = MqttClient(f"vf-ci-{time.time_ns()}")
    client.subscribe(topic, qos=1)
    try:
        if not client.start(5):
            raise RuntimeError("MQTT broker not reachable")
        message = client.get(timeout=3)
        return (message.json() or {}) if message else {}
    finally:
        client.stop()


def check_factory_online() -> str | None:
    status = _retained(Uns.load().status_topic)
    return None if status.get("v") == "online" else f"UNS status {status}"


def check_cpu_linked() -> str | None:
    async def read():
        async with Client("opc.tcp://localhost:4840/vf/plc01", timeout=5) as client:
            ns = await client.get_namespace_index("urn:virtual-factory:plant01:line01:plc01")
            node = client.get_node(ua.NodeId("PLC01.Diagnostics.CpuConnected", ns))
            return (await node.read_data_value(raise_on_bad_status=False)).Value.Value
    return None if asyncio.run(read()) else "PLC CPU (Godot) not linked to plc-comm"


def check_earlier_session_passport() -> str | None:
    started = _retained(Uns.load().session_topic).get("started", "")
    earlier = [p for p in _passports()
               if p.get("dppStatus") == "Active" and started and p.get("lastUpdate", "") < started]
    return None if earlier else f"no Active passport older than the session start {started!r}"


def check_footprint() -> str | None:
    recent = _get("http://localhost:8097/api/footprints", limit=50)
    primary = [f for f in recent if any(c.get("dataQuality") == "primary" for c in f["components"])]
    return None if primary else f"{len(recent)} footprints, none with supplier primary data"


def check_prognosis() -> str | None:
    state = _get("http://localhost:8094/api/components/GR01")
    return None if state.get("prognosis") is not None else "GR01 has no prognosis yet"


def check_alarm_norm() -> str | None:
    alarms = _get("http://localhost:8099/api/alarms", all="true")
    state = next((a["state"] for a in alarms if a["code"] == 201), "NORM")
    return None if state == "NORM" else f"alarm 201 {state}"


def check_historian_session() -> str | None:
    rows = InfluxClient("http://localhost:8181", HistorianConfig.load().database).query(
        "SELECT max(session) AS sid FROM plc01")
    return None if rows and rows[0].get("sid") else "historian has no PLC01 session"


def factory_checks() -> dict[str, Check]:
    return {"factory online (UNS)": check_factory_online, "PLC CPU linked (OPC UA)": check_cpu_linked,
            "passport of an earlier session": check_earlier_session_passport,
            "footprint with supplier data": check_footprint, "GR01 prognosis": check_prognosis,
            "historian session": check_historian_session, "alarm 201 NORM": check_alarm_norm}


# -- skips ------------------------------------------------------------------------------------------------

def check_skips(report: Path, allowed: list[str]) -> int:
    cases = ET.parse(report).getroot().iter("testcase")
    ran, skipped = 0, []
    for case in cases:
        ran += 1
        node = f"{case.get('classname')}::{case.get('name')}"
        for skip in case.findall("skipped"):
            if not any(a in node for a in allowed):
                skipped.append(f"{node}: {skip.get('message', '')}")
    for line in skipped:
        print(f"  SKIPPED (not allowed in CI)  {line}")
    print(f"{ran} integration tests, {len(skipped)} disallowed skips")
    return 1 if skipped or ran == 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["stack", "shipped", "factory", "skips"])
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--allow", action="append", default=[])
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)  # reconnect chatter of the probes' MQTT / OPC UA clients
    if args.command == "skips":
        return check_skips(args.report, args.allow)
    checks = {"stack": stack_checks, "shipped": lambda: {"Active passport": check_shipped},
              "factory": factory_checks}[args.command]()
    print(f"gate '{args.command}' (timeout {args.timeout:.0f} s)", flush=True)
    return 0 if gate(checks, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main())
