# ADR-0012: Control Components with PackML state on the asset interface

- Status: accepted; runtime use refined by [ADR-0020](0020-control-component-and-aid-drive-commands.md) (the ops
  gateway resolves its endpoints from the Control Component Instance, skills are executable via `ExecuteSkill`,
  additional endpoints `ContainerExchange`/`AutoExchange`, skill → endpoint references `UsesEndpoints`)
- Date: 2026-10-03

## Context
The line controller (PLC program) and the robot application should be represented as control components in the AAS:
skills and operation modes, and a state machine (PackML) that agents can observe and command. IDTA Control Component
Type/Instance 2.0 describes skills, operation modes, interfaces and errors, but has no elements for the runtime
execution state.

## Decision
- **ControlComponentType** in the type AAS (LC10_TYPE, UR5E_TYPE): skills (Produce, ExchangeContainer; PickAndPlace,
  MoveHome), interface profiles (ISA-TR88.00.02 PackML; VF job handshake) and errors.
- **ControlComponentInstance** in the instance AAS (PLC01, RB01): Type reference, skill instances, and `Endpoints`
  that reference the generated **Asset Interfaces Description**: the MQTT interface with the property `packml_state`
  and the action `packml_command` (UNS topics).
- The live PackML state flows PLC → MQTT → data bridge → `OperationalData.OperatingState` (with an AIMC lookup
  transformation of the state numbers). Commands flow AAS Operation (M4, delegated) → ops gateway → MQTT → PLC.

## Consequences
+ Conforms to Control Component 2.0 and keeps runtime state on the interface, as real control components do (e.g.
  OPC UA PackML).
+ Agents can discover skills in the AAS and find the endpoint to observe or command via standard references.
− Two places to look (Control Component submodel for capabilities, AID/OperationalData for state). The references
  connect them explicitly.
