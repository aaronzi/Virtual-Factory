"""HTTP endpoint for BaSyx Go operation delegation (qualifier `invocationDelegation`).

BaSyx POSTs the input OperationVariables (JSON array of {"value": <SubmodelElement>}) to
/operations/<OperationIdShort> and returns the response array as the operation's output arguments.

Secure profile (ADR-0027): BaSyx Go forwards the caller's `Authorization` header to the delegation target,
so the gateway validates that bearer token itself (vf_common.jwt_auth) and accepts only the roles in
COMMANDERS - the same roles that the ABAC rules of the AAS environment allow to invoke LineControl.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from vf_common.jwt_auth import InvalidToken, JwtVerifier, bearer

from .gateway import LineGateway, Result
from .skills import SkillExecutor

log = logging.getLogger("ops-gateway")
COMMANDERS = ("operator", "planner", "maintenance", "svc-mes", "svc-maintenance")


WITH_STATE = {"ExecutePackMLCommand", "ExecuteSkill", "SetUnitMode"}


def operations(gw: LineGateway) -> dict:
    skills = SkillExecutor(gw)
    return {
        "ExecutePackMLCommand": lambda a: gw.packml_command(str(a.get("Command", ""))),
        "SetUnitMode": lambda a: skills.set_unit_mode(str(a.get("Mode") or "")),
        # the operation is a shortcut for the skill: container checked against the skill's parameter values
        "ExchangeContainer": lambda a: skills.execute("ExchangeContainer", "",
                                                      {"container": a.get("Container") or ""}),
        "SetAutoExchange": lambda a: gw.set_auto_exchange(str(a.get("Enabled", "")).lower() in ("true", "1")),
        "ExecuteSkill": lambda a: skills.execute(str(a.get("Skill") or ""), str(a.get("Mode") or ""),
                                                 a.get("Parameters")),
    }


def health(gw: LineGateway) -> dict:
    config = gw.config
    return {"status": "ok" if config else "unconfigured", "packml_state": gw.state,
            "unit_mode": gw.values.get("UnitMode"),
            "controller": config.controller if config else None,
            "endpoints": {k: {"kind": a.kind, "affordance": a.name, "protocol": a.protocol,
                              "server": a.base if a.protocol == "opcua" else None, "topic": a.form.topic,
                              "ack": a.ack.topic if a.ack else None}
                          for k, a in (config.endpoints.items() if config else [])},
            "skills": sorted(config.skills) if config else []}


def output_variables(result: Result, with_state: bool) -> list[dict]:
    out = [_prop("Accepted", "xs:boolean", "true" if result.accepted else "false")]
    if with_state:
        out.append(_prop("State", "xs:string", result.state))
    out.append(_prop("Message", "xs:string", result.message))
    return [{"value": p} for p in out]


def input_arguments(body: bytes) -> dict[str, str]:
    data = json.loads(body or b"[]")
    if isinstance(data, dict):  # tolerate an invocation request body
        data = data.get("inputArguments", [])
    return {v["value"]["idShort"]: v["value"].get("value")
            for v in data if isinstance(v, dict) and "value" in v}


def authorize(verifier: JwtVerifier | None, authorization: str | None) -> tuple[int, str]:
    """(0, caller) if the call may proceed, else (HTTP status, reason)."""
    if verifier is None:
        return 0, "anonymous"
    try:
        caller = verifier.verify(bearer(authorization))
    except InvalidToken as exc:
        return 401, f"authentication required: {exc}"
    if not caller.has_any(COMMANDERS):
        return 403, f"{caller.name} may not command the line (roles: {', '.join(COMMANDERS)})"
    return 0, caller.name


def make_handler(gw: LineGateway, verifier: JwtVerifier | None = None) -> type[BaseHTTPRequestHandler]:
    ops = operations(gw)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send(200, health(gw))
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            name = self.path.rstrip("/").rsplit("/", 1)[-1]
            if not self.path.startswith("/operations/") or name not in ops:
                self._send(404, {"error": f"unknown operation {name}"})
                return
            status, caller = authorize(verifier, self.headers.get("Authorization"))
            if status:
                log.warning("%s refused: %s", name, caller)
                self._send(status, {"error": caller})
                return
            try:
                args = input_arguments(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except (ValueError, KeyError, TypeError) as exc:
                self._send(400, {"error": f"invalid operation variables: {exc}"})
                return
            result = ops[name](args)
            log.info("%s(%s) by %s -> accepted=%s %s", name, args, caller, result.accepted, result.message)
            self._send(200, output_variables(result, with_state=name in WITH_STATE))

        def _send(self, status: int, body) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            log.debug(fmt, *args)

    return Handler


def serve(gw: LineGateway, port: int, verifier: JwtVerifier | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), make_handler(gw, verifier))


def _prop(id_short: str, value_type: str, value: str) -> dict:
    return {"modelType": "Property", "idShort": id_short, "valueType": value_type, "value": value}

