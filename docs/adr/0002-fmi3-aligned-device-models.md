# ADR-0002: FMI-3-aligned device models in GDScript

- Status: accepted
- Date: 2026-10-03

## Context

Device simulation models should use an interface closely aligned with FMI 3.0 (requirement FR-10), even though
they are implemented in GDScript. Real FMUs are C binaries loaded via a shared library, which GDScript cannot do.

## Decision

- Base class `Fmi3CoSimulation` mirrors the FMI 3.0 **Co-Simulation** C API one-to-one (snake_case names):
  instantiate, enter/exit initialization mode, `do_step`, typed get/set by value reference, get/set FMU state,
  reset, terminate, free instance, plus the `fmi3Status` enum.
- Each model ships a genuine FMI 3.0 `modelDescription.xml`. It is the single source for variables, value
  references, causality, variability, units and start values, and is validated against the official XSD in CI.
- A fixed-step Gauss-Seidel master drives all models. Signal connections come from the factory layout.
- **Out of scope:** Model Exchange, Scheduled Execution, FMI 3 Clocks, binary variables and directional
  derivatives. Discrete events use Boolean/Int outputs with `variability="discrete"`.

## Consequences

- \+ Models are pure logic: headless-testable and replaceable without changing anything else.
- \+ A later `Fmi3NativeAdapter` (GDExtension around the FMI 3 C API) can run real `.fmu` files behind the same interface.
- − Some FMI concepts are simplified (no clocks). This is documented in the interface docs.
