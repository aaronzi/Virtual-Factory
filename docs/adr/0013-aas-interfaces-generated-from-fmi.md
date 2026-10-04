# ADR-0013: AAS interface descriptions generated from FMI model descriptions

- Status: accepted
- Date: 2026-10-03

## Context

Each device publishes its FMI outputs via MQTT (UNS). The AAS must describe these interfaces (IDTA Asset Interfaces
Description) and how they map to submodel elements (IDTA AIMC), and process values need semantics (unit, meaning).
Hand-maintaining this per device would drift from the simulation.

## Decision

- The provisioner generates, per device, from `modelDescription.xml` + `godot/config/uns.json` + the asset data:
  - **AID** (MQTT interface; one WoT property per FMI output with JSON payload `{v, ts}`, unit, and forms with topic,
    retain and QoS; actions for writable inputs)
  - **AIMC 2.0** (one mapping per stored output → OperationalData/EnergyConsumption element; state codes are mapped by a
    Lua transformation with the template's `aimc_main(sources)` entry point, generated from `device.state.map`)
  - **OperationalData** process values with **generated concept descriptions** (`…/cd/fmi/<Model>/<variable>`, unit
    and definition from the model description)
  - **SimulationModels** ports and model file
  - TimeSeries (record structure with UtcTime + one variable per output, LinkedSegment to the historian;
    [ADR-0019](0019-historian-timeseries-linked-segment.md), which also limits OperationalData/AIMC to discrete
    outputs)
- The AIMC bridge (M4, [ADR-0015](0015-aimc-bridge.md)) configures itself by reading the AIMC/AID from BaSyx.

## Consequences

- \+ The FMI model description is the single source of truth for device interfaces in the simulation, MQTT and AAS.
  A test asserts that the AID properties equal the FMI outputs and the AIMC sources the outputs the AAS stores
  (discrete outputs + energy/hours/state, ADR-0019).
- \+ New device types get correct AAS interfaces without extra authoring.
- − Variable names become AAS idShorts and topic segments, so FMI variable names must be idShort-safe (letters, digits,
  `_`, at least 2 characters).
