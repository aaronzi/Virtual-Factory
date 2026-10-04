# ADR-0020: Control Component and AID configure the command and event paths

- Status: accepted
- Date: 2026-10-03
- Refines: [ADR-0012](0012-control-component-packml-on-interface.md),
  [ADR-0017](0017-aas-operations-delegated.md); extends [ADR-0013](0013-aas-interfaces-generated-from-fmi.md)

## Context

A review found parts of the AAS model decorative. The Control Component Instance of PLC01 (skills, endpoints) and the
AID *actions* and *events* were generated, but nothing read them at runtime. The ops gateway and the MES took
their MQTT topics straight from `godot/config/uns.json`. Only the bridge configured itself from the AAS (AID
properties + AIMC, ADR-0015). Also, the UNS command acknowledgements (`{root}/{device}/cmd-resp/{variable}`) were
not described in the AAS at all.

## Decision

**Ops gateway: resolution chain.** At start-up the gateway resolves `LINE01/LineControl.ControlComponent` →
`PLC01/ControlComponentInstance` → `Endpoints.<name>.EndpointReference` → AID affordance of PLC01. From the AID
it takes the topic (`forms.href`), QoS, retain flag, content type and payload keys (`input`/`output` schema,
`properties.Value.key` for the state property). It does this again on BaSyx change events for exactly the
submodels it read (LineControl, CC instance, AID) and every 5 min.

- The endpoint idShorts form the contract between gateway and AAS: `PackMLState` (property), `PackMLCommand`,
  `ContainerExchange`, `AutoExchange` (actions). The last two are new in PLC01, with a new interface
  `ContainerHandling` in the type LC10_TYPE.
- **No fallback to uns.json.** BaSyx is the only caller of the gateway (invocation delegation), so an unreachable
  AAS server means no operations arrive anyway. The gateway rejects operations with an explanation until the
  configuration is resolved. It retries every 5 s and logs an error per attempt. A failed reload keeps the last
  good configuration.

**Acknowledgement in the AID.** Each generated action affordance now has:

- `input` (td:hasInputSchema): keys `v`, `corr`, `source`.
- `output` (td:hasOutputSchema): the ack payload `corr`, `accepted`, `reason`, `v`, `ts`.
- `synchronous` = false.
- `forms` (`op` = `invokeaction`, `mqv_controlPacket` publish).
- `ackForms`: a second TD form (semanticId td:hasForm) with `op` = `queryaction`, the cmd-resp topic and
  `mqv_controlPacket` subscribe.
- Event forms carry `op` = `subscribeevent`.

Why this representation:

- In W3C WoT TD 1.1 one affordance may have several forms, told apart by `op`. `queryaction` is the TD 1.1
  operation for querying the status of an action invocation, which is what the ack is. `synchronous: false`
  states that the result does not come back on the invoking request.
- AID 1.1 maps only one form per interaction (`forms` collection, mandatory). The second form therefore is a
  sibling collection with the same semanticId. `actions` is an open collection, so AID consumers that ignore it
  still see a valid, unchanged primary form.
- Rejected alternatives:
  - `additionalResponses` (TD `AdditionalExpectedResponse`) has only `success`, `contentType` and `schema`, no
    target, so it cannot carry the topic.
  - The WoT MQTT binding defines no response-topic term.
  - MQTT 5 response topics are not available (Mosquitto clients here speak 3.1.1).
  - Separate ack *properties* would mix non-FMI interactions into `properties`, which ADR-0013 (and its test)
    keep equal to the FMI outputs.

**Skills → endpoints.** Control Component 2.0 relates skills only to skills (`Uses`) and endpoints only to
interfaces. There is no skill → endpoint element. Each skill instance therefore has an additional
`SubmodelElementList UsesEndpoints` (semanticId `…/cd/ControlComponent/UsesEndpoints`) of ReferenceElements to
`Endpoints.<name>` (Produce → PackMLCommand, PackMLState, AutoExchange; ExchangeContainer → ContainerExchange). The
AAS engine now resolves `{ref: …}` in extra ReferenceElements and in extra lists of them.

**ExecuteSkill.** LineControl 1.1 adds `ExecuteSkill(Skill, Mode, Parameters)` → `Accepted`, `State`, `Message`
(delegated like the other operations).

- The gateway reads skills, `Disabled`, `Modes` and `Parameters` (Direction, Type, Min/Max, enumerated values)
  from the CC instance and validates the request against them.
- What a skill *does* on this controller is implemented in the gateway:
  - `Produce` → Clear/Reset/Start/Unhold/Unsuspend until EXECUTE. Input parameters are sent first, through the
    used endpoint whose AID action has the parameter's name (e.g. `auto_exchange`). Parameters without such an
    endpoint (`belt_speed`) are rejected as not settable at runtime.
  - `ExchangeContainer` → the skill's single command endpoint.
- The existing `ExchangeContainer` operation is now a shortcut for that skill, so the container number is
  validated against the skill's parameter values.

**MES events.** The MES discovers its event topics from every AID on the server (`InteractionMetadata.events.*.forms`;
the AID 1.1 semanticId is a ModelReference, so both reference forms are queried). It maps the affordance name to
BPMN messages and reloads on AID change events and every 5 min. Topics not described in the AAS are ignored. The
**session birth** topic stays in the UNS registry: it is a namespace topic of the Godot gateway, not an
interaction of an asset, and no AAS describes "the factory run".

## Consequences

- \+ The AAS is the configuration of the command, acknowledgement and event paths. Changing an AID href in BaSyx
  re-routes commands (gateway) or event subscriptions (MES) within seconds, without a restart (demonstrated in
  the M7 verification).
- \+ Skills in the Control Component are invocable and their parameter descriptions are enforced. Agents can
  discover a skill and call it through one operation.
- \+ The external API (ExecutePackMLCommand, ExchangeContainer, SetAutoExchange) is unchanged. BPMN and Node-RED keep
  working.
- − The endpoint idShorts and the skill executors are a contract in code. A new skill needs an executor in the
  gateway (reported as such when invoked).
- − `UsesEndpoints` and `ackForms` are extensions beyond the IDTA templates. They are documented here and in
  aas-model.md and carry WoT/VF semantic ids. The `UsesEndpoints` concept id has no concept description yet.
- − Skill modes are validated but not applied: the PLC has no unit-mode endpoint (open issue O35).
- − The MES still takes the PLC01 KPI telemetry topics and the session topic from the UNS registry.
