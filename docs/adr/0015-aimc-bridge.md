# ADR-0015: Own AIMC-driven bridge instead of the BaSyx DataBridge or Node-RED

- Status: accepted
- Date: 2026-10-03

## Context
Live shop-floor values must reach the AAS (OperationalData, EnergyConsumption). The BaSyx (Java) DataBridge is
archived and deprecated. Node-RED would work, but its flows are wired by hand per device and stored outside the AAS,
duplicating the mapping that the AAS already contains (AIMC, ADR-0013).

## Decision
- A small Python service `bridge` interprets **IDTA AIMC 2.0 + AID 1.1** from the AAS server at runtime: for every
  MappingConfiguration it resolves the source (AID property → MQTT topic `forms.href`, JSON key from the nested
  `Value.key`), the sink (ModelReference → submodel + idShort path, value type from the sink element) and the
  optional transformation.
- Transformations are Lua code with the `aimc_main(sources)` entry point defined by the AIMC template; they are
  executed in a sandbox (lupa; only string/table/math and pure functions, no os/io/require/Python access).
- Write policy (risk R5): discrete values immediately on change; numbers at most once per second per element and
  outside a deadband; value-only PATCH.
- BaSyx MQTT eventing is enabled; the bridge reloads its mappings when an AIMC or AID submodel changes (events carry
  only the submodel, so the bridge re-reads it) and every 5 minutes as a fallback.
- Blob values are fetched with `extent=withBlobValue` (BaSyx omits them by default).

## Consequences
+ "The AAS configures the integration": a new device needs no bridge change; editing an AIMC in the AAS changes the
  data flow at runtime (good teaching example).
+ No duplicated mapping configuration outside the AAS.
− Own code to maintain (~300 lines, unit-tested against the generated AAS). The broker address comes from the
  deployment, not from the AID `base` (which describes the host view, `mqtt://localhost:1883`).
− Node-RED remains an option as a learner sandbox (M5), outside the core data path.
