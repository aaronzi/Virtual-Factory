"""Command and state paths of the line controller, resolved from the AAS (ADR-0020):

    LINE01/LineControl.ControlComponent -> PLC01/ControlComponentInstance
        Endpoints.<name>.EndpointReference
            -> PLC01/AssetInterfacesDescription ...InteractionMetadata.(properties|actions).<affordance>
            -> forms (topic, QoS, retain), payload keys (input/output schema), ackForms (ack topic)
        Skills.<name>: Disabled, Modes, Parameters, UsesEndpoints -> Endpoints.<name>

The endpoint idShorts are the contract with the gateway: PackMLState (property), PackMLCommand,
ContainerExchange, AutoExchange (actions). Topics, flags and keys come only from the AID.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vf_common.aid import AasSource, Affordance, Resolver, child, value_of

STATE, PACKML, EXCHANGE, AUTO_EXCHANGE = "PackMLState", "PackMLCommand", "ContainerExchange", "AutoExchange"
LIMITS = ("Min", "Max", "Default", "Unit")


@dataclass(frozen=True)
class Parameter:
    name: str
    direction: str
    type: str
    values: dict[str, str] = field(default_factory=dict)  # Values: idShort -> lexical value

    def convert(self, raw):
        """Raw input (JSON value or string) -> typed value; ValueError with a reason if it does not fit."""
        try:
            value = _typed(self.type, raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.name} = {raw!r} is not of type {self.type}") from exc
        for bound, ok in (("Min", lambda lim: value >= lim), ("Max", lambda lim: value <= lim)):
            if bound in self.values and not ok(_typed(self.type, self.values[bound])):
                raise ValueError(f"{self.name} = {value} outside {bound} {self.values[bound]}")
        allowed = {k: _typed(self.type, v) for k, v in self.values.items() if k not in LIMITS}
        if allowed and value not in allowed.values():
            options = ", ".join(f"{v} ({k})" for k, v in allowed.items())
            raise ValueError(f"{self.name} = {value} is not one of {options}")
        return value


@dataclass(frozen=True)
class Skill:
    name: str
    disabled: bool
    modes: list[str]
    parameters: dict[str, Parameter]
    endpoints: list[str]  # idShorts of the Endpoints the skill uses


@dataclass(frozen=True)
class ControlConfig:
    controller: str
    endpoints: dict[str, Affordance]
    skills: dict[str, Skill]
    sources: frozenset[str]  # ids of the submodels the configuration was read from

    def describe(self) -> list[str]:
        lines = []
        for name, aff in self.endpoints.items():
            ack = f", ack {aff.ack.topic}" if aff.ack else ""
            lines.append(f"{name} -> {aff.kind} {aff.name}: {aff.form.topic} (qos {aff.form.qos}, "
                         f"retain {str(aff.form.retain).lower()}, value key '{aff.key('Value', 'v')}'{ack})")
        for skill in self.skills.values():
            lines.append(f"skill {skill.name}: modes {', '.join(skill.modes)}; parameters "
                         f"{', '.join(skill.parameters) or '-'}; "
                         f"endpoints {', '.join(skill.endpoints) or '-'}"
                         + (" (disabled)" if skill.disabled else ""))
        return lines


def resolve(source: AasSource, line_control_id: str) -> ControlConfig:
    """Raises LookupError (or KeyError/TypeError on malformed elements) if the chain is incomplete."""
    resolver = Resolver(source)
    line_control = resolver.submodel(line_control_id)["submodelElements"]
    cc_ref = value_of(line_control, "ControlComponent")
    if not cc_ref:
        raise LookupError(f"{line_control_id}: no ControlComponent reference")
    cc = resolver.element(cc_ref)["value"]
    endpoints = {}
    for endpoint in child(cc, "Endpoints").get("value") or []:
        endpoints[endpoint["idShort"]] = resolver.affordance(value_of(endpoint["value"], "EndpointReference"))
    skills = [_skill(s) for s in child(cc, "Skills").get("value") or []]
    return ControlConfig(_controller(source, value_of(line_control, "Controller")), endpoints,
                         {s.name: s for s in skills}, frozenset(resolver.sources))


def _controller(source: AasSource, ref: dict | None) -> str:
    if not ref:
        return "?"
    shell = source.get_shell(ref["keys"][0]["value"])
    return shell["idShort"] if shell else ref["keys"][0]["value"]


def _skill(element: dict) -> Skill:
    elements = element.get("value") or []
    modes = [m.get("value") for m in child(elements, "Modes").get("value") or []]
    params = [_parameter(p) for p in child(elements, "Parameters").get("value") or []]
    uses = child(elements, "UsesEndpoints", required=False) or {}
    endpoints = [ref["value"]["keys"][-1]["value"] for ref in uses.get("value") or [] if ref.get("value")]
    return Skill(element["idShort"], str(value_of(elements, "Disabled", "false")).lower() == "true",
                 [m for m in modes if m], {p.name: p for p in params}, endpoints)


def _parameter(element: dict) -> Parameter:
    elements = element.get("value") or []
    values = {v["idShort"]: v.get("value") for v in child(elements, "Values").get("value") or []
              if v.get("modelType") == "Property"}
    return Parameter(element["idShort"], value_of(elements, "Direction", "In"),
                     value_of(elements, "Type", "xs:string"), values)


def _typed(value_type: str, raw):
    if value_type in ("xs:int", "xs:integer", "xs:long", "xs:short"):
        if isinstance(raw, bool) or (isinstance(raw, float) and not raw.is_integer()):
            raise ValueError(f"{raw!r} is not an integer")
        return int(raw)
    if value_type in ("xs:double", "xs:float", "xs:decimal"):
        return float(raw)
    if value_type == "xs:boolean":
        if str(raw).lower() in ("true", "1"):
            return True
        if str(raw).lower() in ("false", "0"):
            return False
        raise ValueError(f"{raw!r} is not a boolean")
    return str(raw)
