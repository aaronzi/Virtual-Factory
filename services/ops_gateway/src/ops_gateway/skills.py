"""ExecuteSkill: runs a skill of the Control Component Instance (ADR-0020).

What a skill is, which modes and parameters it has and which endpoints it uses is read from the AAS
(`ControlConfig.skills`); how a skill is carried out on this controller is implemented here:

    Produce            bring the line to EXECUTE (Clear / Reset / Start / Unhold / Unsuspend as the PackML
                       state requires); input parameters that an endpoint of the skill accepts (AID action
                       with the parameter's name, e.g. auto_exchange) are sent first
    ExchangeContainer  send `container` to the skill's command endpoint (klt exchange)
"""

from __future__ import annotations

import json

from .control import ControlConfig, Skill
from .gateway import NOT_CONFIGURED, LineGateway, Result
from .packml import state_name

# next PackML command on the way to EXECUTE
PRODUCE_STEP = {"ABORTED": "Clear", "STOPPED": "Reset", "COMPLETE": "Reset", "IDLE": "Start",
                "HELD": "Unhold", "SUSPENDED": "Unsuspend"}
TRANSIENT = {"CLEARING", "STARTING", "RESETTING", "UNHOLDING", "UNSUSPENDING", "STOPPING", "ABORTING",
             "HOLDING", "SUSPENDING", "COMPLETING"}


class SkillExecutor:
    def __init__(self, gateway: LineGateway, auto_start_wait: float = 2.0):
        self.gw, self.auto_start_wait = gateway, auto_start_wait
        self.handlers = {"Produce": self._produce, "ExchangeContainer": self._exchange_container}

    def execute(self, name: str, mode: str = "", parameters=None) -> Result:
        config = self.gw.config
        if config is None:
            return Result(False, NOT_CONFIGURED)
        skill = config.skills.get(name)
        if skill is None:
            return Result(False, f"unknown skill '{name}' (skills of {config.controller}: "
                                 f"{', '.join(config.skills) or 'none'})")
        if skill.disabled:
            return Result(False, f"skill {name} is disabled in the Control Component Instance")
        mode = mode or (skill.modes[0] if skill.modes else "")
        if skill.modes and mode not in skill.modes:
            return Result(False, f"mode '{mode}' not offered by {name} (modes: {', '.join(skill.modes)})")
        try:
            values = check_parameters(skill, parse_parameters(parameters))
        except ValueError as exc:
            return Result(False, f"{name}: {exc}")
        handler = self.handlers.get(name)
        if handler is None:
            return Result(False, f"skill {name} is described in the AAS, but the ops gateway has no "
                                 "executor for it")
        result = handler(config, skill, values)
        result.message = f"{name} ({mode}): {result.message}"
        return result

    def _produce(self, config: ControlConfig, skill: Skill, values: dict) -> Result:
        for name, value in values.items():
            endpoint = parameter_endpoint(config, skill, name)
            if endpoint is None:
                return Result(False, f"parameter {name} cannot be set at runtime (no endpoint of the skill "
                                     "accepts it)", self._state())
            sent = self.gw.send(endpoint, value)
            if not sent.accepted:
                return Result(False, f"{name}: {sent.message}", self._state())
        steps: list[str] = []
        for _ in range(6):
            self.gw.wait_state(lambda s: s not in TRANSIENT, self.gw.state_timeout)
            state = self._state()
            if state == "EXECUTE":
                done = " -> ".join(steps) if steps else "already in EXECUTE"
                return Result(True, f"line in production ({done})", state)
            if state == "IDLE" and steps and steps[-1] == "Reset" and \
                    self.gw.wait_state(lambda s: s != "IDLE", self.auto_start_wait):
                continue  # the controller starts by itself after Reset (auto_start)
            command = PRODUCE_STEP.get(state)
            if command is None:
                return Result(False, f"cannot start production from state {state}", state)
            result = self.gw.packml_command(command)
            steps.append(command)
            if not result.accepted:
                return Result(False, f"{' -> '.join(steps)} failed: {result.message}", result.state)
        return Result(False, f"EXECUTE not reached ({' -> '.join(steps)})", self._state())

    def _exchange_container(self, config: ControlConfig, skill: Skill, values: dict) -> Result:
        extra = sorted(set(values) - {"container"})
        if extra:
            return Result(False, f"parameter {', '.join(extra)} cannot be set at runtime", self._state())
        if "container" not in values:
            return Result(False, "parameter container is required", self._state())
        commands = [e for e in skill.endpoints if config.endpoints.get(e) and
                    config.endpoints[e].kind == "action"]
        if len(commands) != 1:
            return Result(False, f"skill needs exactly one command endpoint (UsesEndpoints: "
                                 f"{skill.endpoints})")
        result = self.gw.send(commands[0], values["container"])
        return Result(result.accepted, result.message, self._state())

    def _state(self) -> str:
        return state_name(self.gw.state)


def parse_parameters(raw) -> dict:
    """Parameters input: JSON object (string or dict); empty = none."""
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"Parameters is not a JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Parameters must be a JSON object, e.g. {\"container\": 1}")
    return data


def check_parameters(skill: Skill, raw: dict) -> dict:
    values = {}
    for name, value in raw.items():
        parameter = skill.parameters.get(name)
        if parameter is None:
            known = ", ".join(skill.parameters) or "none"
            raise ValueError(f"unknown parameter '{name}' (parameters: {known})")
        if parameter.direction != "In":
            raise ValueError(f"parameter {name} is an output (Direction {parameter.direction})")
        values[name] = parameter.convert(value)
    return values


def parameter_endpoint(config: ControlConfig, skill: Skill, parameter: str) -> str | None:
    """Endpoint of the skill whose AID action has the parameter's name (e.g. auto_exchange)."""
    return next((e for e in skill.endpoints if config.endpoints.get(e)
                 and config.endpoints[e].kind == "action" and config.endpoints[e].name == parameter), None)
