# FMI-3-aligned device model interface

All device behaviour models and the PLC program implement `Fmi3CoSimulation`
(`godot/core/fmi/fmi3_co_simulation.gd`). Their interface is described by a genuine
**FMI 3.0 `modelDescription.xml`**, validated in CI against the official XSD (`tools/schemas/fmi3`,
FMI 3.0.2) and checked for consistency (unique VRs and names, exactly one independent variable,
units defined, `ModelStructure/Output` lists all outputs). Rationale: [ADR-0002](../adr/0002-fmi3-aligned-device-models.md).

## API mapping

| FMI 3.0 C function | GDScript | Notes |
|---|---|---|
| `fmi3InstantiateCoSimulation` | `instantiate(instance_name, model_description, instantiation_token := "", logging_on := false) -> Status` | Model description object instead of a resource path; token checked if given |
| `fmi3EnterInitializationMode` | `enter_initialization_mode(start_time, stop_time, tolerance)` | |
| `fmi3ExitInitializationMode` | `exit_initialization_mode()` | calls `_on_initialize()` |
| `fmi3DoStep` | `do_step(t, h, no_set_fmu_state_prior) -> Fmi3DoStepResult` | `status, event_handling_needed, terminate_simulation, early_return, last_successful_time` |
| `fmi3GetFloat64/Int32/UInt64/Boolean/String` | `get_float64(vrs: PackedInt64Array)`, … | status in `last_status` |
| `fmi3SetFloat64/…` | `set_float64(vrs, values) -> Status`, … | causality/variability rules enforced |
| `fmi3GetFMUState/SetFMUState` | `get_fmu_state() -> Dictionary`, `set_fmu_state(state)` | internal state via `_save/_load_internal_state()` |
| `fmi3Reset`, `fmi3Terminate`, `fmi3FreeInstance` | `reset()`, `terminate()`, `free_instance()` | |
| `fmi3Status` | `Fmi3.Status { OK, WARNING, DISCARD, ERROR, FATAL }` | |

Convenience (not in FMI): `get_value(name)`, `set_value(name, value)`, `get_value_by_vr()`,
`set_value_by_vr()` — same rules, used by the master, composition root and tests.

## Settability rules (FMI 3.0 §2.2)

| Phase | Settable |
|---|---|
| Instantiated / Initialization | inputs, parameters (fixed + tunable), structural parameters |
| Step mode | inputs, tunable parameters |
| always | outputs are never settable from outside (`_set_var()` internally) |

## Data types

| FMI type | GDScript | Used for |
|---|---|---|
| Float64 | `float` (64 bit) | physical quantities (SI units, declared in `UnitDefinitions`) |
| Int32 / UInt64 | `int` (64 bit) | counters, enumerations (states, variants, PackML) |
| Boolean | `bool` | discrete signals |
| String | `String` | serial numbers |

Units used: s, m, m/s, m/s², rad, rad/s, rad/s², W, kWh, h, Nl, deg, cm³/min.

## Co-simulation master

`CoSimMaster` (`godot/core/fmi/co_sim_master.gd`): fixed step (physics tick, 1/60 s), Gauss-Seidel in
layout order with the PLC last. Before an instance steps, its connected inputs are copied from the source
outputs (`connect_variables("SRC.out", "DST.in")`, type- and causality-checked). Devices therefore see PLC
outputs with one step delay (≈ PLC I/O delay), the PLC sees device outputs of the same step.

## Simplifications (documented deviations)

- Co-Simulation only. Model Exchange, Scheduled Execution, Clocks, Binary, array variables, directional
  derivatives and `fmi3UpdateDiscreteStates`/event mode are not implemented.
- Discrete events are modelled as Boolean outputs or counters (`release_count`, `switch_count`), which
  are robust against sampling.
- The robot FMU state snapshot does not include a running job (snapshots are meant between jobs).
- Godot's `Transform3D` is single precision; kinematic residuals ≤ 0.2 mm near singularities.

## Device catalogue

Generated: [device-catalog.md](device-catalog.md).
