# ADR-0008: PLC program as an FMI co-simulation slave

- Status: accepted
- Date: 2026-10-03

## Context

The line needs a controller with realistic behaviour: a cyclic scan, standard function blocks, PackML. It must be
wired to the devices without the controller knowing device classes (ADR-0006).

## Decision

- A PLC program extends `PlcProgram`, which extends `Fmi3CoSimulation`. Its FMI variables are the **process image**:
  inputs, outputs and parameters, declared in its own `modelDescription.xml`.
- `do_step(h)` runs `h / scan_time` scans (default 10 ms). IEC 61131-3 FBs (TON, TOF, TP, R_TRIG, F_TRIG, CTU)
  and a PackML state machine live in `core/plc`.
- Devices and the PLC are wired with the same `connections` mechanism in the layout. The PLC is stepped last
  (Gauss-Seidel), so devices see PLC outputs one step later, like real I/O update delays.

## Consequences

- \+ Uniform wiring and testing. The PLC can be tested headless with simulated inputs.
- \+ A real PLC (OpenPLC/Codesys via Modbus/OPC UA) could replace it behind the same variables later.
- − PLC logic is GDScript, not IEC Structured Text. The structure (FBs, step chain, scan) mirrors IEC so students
  can map it.
