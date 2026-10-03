"""ExecuteSkill: runs a skill of the Control Component Instance (ADR-0020).

What a skill is, which modes and parameters it has and which endpoints it uses is read from the AAS
(`ControlConfig.skills`); how a skill is carried out on this controller is implemented here:

    Produce            bring the line to EXECUTE (Clear / Reset / Start / Unhold / Unsuspend as the PackML
                       state requires); input parameters that an endpoint of the skill accepts (AID action
                       with the parameter's name, e.g. auto_exchange) are sent first
    ExchangeContainer  send `container` to the skill's command endpoint (klt exchange)
    Maintain           stop the line (if it is not in a wait state) and switch to the unit mode
                       Maintenance; then send the parameters that confirm maintenance work (e.g.
                       gripper_maintenance_reset = true: AID action of that name, here of robot RB01) -
                       only while stopped in Maintenance

Modes: if the Control Component has the endpoints UnitMode / UnitModeCommand, the requested mode (Production,
Maintenance, Manual = PackML unit modes 1-3) is applied before the skill runs. The controller accepts a unit
mode change only in STOPPED, IDLE or ABORTED, so a running line must be stopped first (Maintain does that
itself). `set_unit_mode` is the LineControl operation SetUnitMode (mode change without a skill).
"""

from __future__ import annotations

import json

from vf_common.packml import UNIT_MODE_CHANGE_STATES, UNIT_MODES, unit_mode_name

from .control import UNIT_MODE, UNIT_MODE_COMMAND, ControlConfig, Skill
from .gateway import NOT_CONFIGURED, LineGateway, Result
from .packml import state_name

# next PackML command on the way to EXECUTE
PRODUCE_STEP = {"ABORTED": "Clear", "STOPPED": "Reset", "COMPLETE": "Reset", "IDLE": "Start",
                "HELD": "Unhold", "SUSPENDED": "Unsuspend"}
STOP_FIRST = {"Maintain"}  # skills that bring the line to a wait state before their unit mode is applied
TRANSIENT = {"CLEARING", "STARTING", "RESETTING", "UNHOLDING", "UNSUSPENDING", "STOPPING", "ABORTING",
             "HOLDING", "SUSPENDING", "COMPLETING"}


class SkillExecutor:
    def __init__(self, gateway: LineGateway, auto_start_wait: float = 2.0, mode_timeout: float = 2.0):
        self.gw, self.auto_start_wait, self.mode_timeout = gateway, auto_start_wait, mode_timeout
        self.handlers = {"Produce": self._produce, "ExchangeContainer": self._exchange_container,
                         "Maintain": self._maintain}

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
        switched = self._stop_for_mode() if name in STOP_FIRST else None
        if switched is None or switched.accepted:
            switched = self._apply_mode(config, mode)
        if switched is not None and not switched.accepted:
            switched.message = f"{name} ({mode}): {switched.message}"
            return switched
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

    def _maintain(self, config: ControlConfig, skill: Skill, values: dict) -> Result:
        state = self._state()
        in_maintenance = UNIT_MODE not in config.endpoints or \
            self.gw.values.get(UNIT_MODE) == UNIT_MODES["Maintenance"]
        if state not in UNIT_MODE_CHANGE_STATES or not in_maintenance:
            return Result(False, f"line not stopped in the unit mode Maintenance (state {state})", state)
        sent = []
        for name, value in values.items():
            if value is False:
                continue  # nothing to confirm
            endpoint = parameter_endpoint(config, skill, name)
            if endpoint is None:
                return Result(False, f"parameter {name}: no endpoint of the skill accepts it", state)
            result = self.gw.send(endpoint, value)
            if not result.accepted:
                return Result(False, f"{name}: {result.message}", state)
            sent.append(f"{name} sent to {endpoint}")
        done = f"; {', '.join(sent)}" if sent else ""
        return Result(True, f"line stopped in maintenance (unit mode Maintenance){done}", state)

    def set_unit_mode(self, mode: str) -> Result:
        """LineControl SetUnitMode: only the mode change (accepted in STOPPED, IDLE, ABORTED)."""
        config = self.gw.config
        if config is None:
            return Result(False, NOT_CONFIGURED)
        if mode not in UNIT_MODES:
            return Result(False, f"unknown unit mode '{mode}' (one of {', '.join(UNIT_MODES)})",
                          self._state())
        result = self._apply_mode(config, mode)
        if result is None:
            return Result(False, f"{config.controller} has no unit mode endpoints (UnitMode, "
                                 "UnitModeCommand)", self._state())
        return result

    def _stop_for_mode(self) -> Result:
        """Brings the line to a state in which the controller accepts a unit mode change (Stop if needed)."""
        self.gw.wait_state(lambda s: s not in TRANSIENT, self.gw.state_timeout)
        if self._state() in UNIT_MODE_CHANGE_STATES:
            return Result(True, f"line in {self._state()}", self._state())
        result = self.gw.packml_command("Stop")
        return result if not result.accepted else Result(True, "Stop executed", result.state)

    def _apply_mode(self, config: ControlConfig, mode: str) -> Result | None:
        """Sets the controller's unit mode (None: the controller has no unit mode endpoints)."""
        if UNIT_MODE_COMMAND not in config.endpoints or UNIT_MODE not in config.endpoints \
                or mode not in UNIT_MODES:
            return None
        target = UNIT_MODES[mode]
        current = unit_mode_name(self.gw.values.get(UNIT_MODE))
        if self.gw.values.get(UNIT_MODE) == target:
            return Result(True, f"unit mode {mode}", self._state())
        if self._state() not in UNIT_MODE_CHANGE_STATES:
            return Result(False, f"unit mode is {current}; the controller changes it only in "
                                 f"{', '.join(sorted(UNIT_MODE_CHANGE_STATES))} (state {self._state()}) - "
                                 "stop the line first", self._state())
        sent = self.gw.send(UNIT_MODE_COMMAND, target)
        if not sent.accepted:
            return Result(False, f"unit mode {mode}: {sent.message}", self._state())
        if self.gw.wait_value(UNIT_MODE, lambda v: v == target, self.mode_timeout):
            return Result(True, f"unit mode {mode}", self._state())
        return Result(False, f"unit mode stays {current} (no change reported within "
                             f"{self.mode_timeout:.0f} s)", self._state())

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
