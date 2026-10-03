# ADR-0006: Composition root and measured dependency rules

- Status: accepted
- Date: 2026-10-03

## Context
Requirements: modular design, optimised coupling and cohesion, ≥ 95 % architecture adherence (NFR-03/04).

## Decision
- Godot modules = top-level folders. `core` has no dependencies. Every other module depends only on `core`.
  Device sub-modules (`devices/<type>`) are isolated from each other.
- `factory` is the **single composition root**. It loads the layout and wires FMI signals, PLC I/O, UNS tags
  and AAS ids.
- There is no global domain event bus. Modules interact through FMI variables and small `core` interfaces.
- The rules live in `docs/architecture/dependency-rules.yaml` and are checked by `tools/arch_check.py` (CI).
  Documented exceptions are allowed but count against the adherence score.
- Complexity limits: gdlint (file ≤ 300 lines, line ≤ 110) plus `tools/complexity_check.py` (function ≤ 40 lines).

## Consequences
+ Coupling is visible and measurable, and new device types are drop-in folders.
− Some wiring code concentrates in `factory`. It must stay declarative/data-driven to avoid a god module.
