# ADR-0009: Physical transport with Jolt rigid bodies

- Status: accepted
- Date: 2026-10-03

## Context
Workpieces must move along the conveyor, accumulate, be detected by sensors, be gripped and drop into containers.
The options were kinematic path following (deterministic, artificial) or rigid-body physics (realistic, small risk
of instability).

## Decision
- Workpieces are `RigidBody3D` (`TrackedItem` contract in core). The belt is a `StaticBody3D` with
  `constant_linear_velocity` set by the conveyor view from the model's `belt_speed`.
- `can_sleep = false` for items: constant surface velocity doesn't wake sleeping bodies (found in M1).
- Grasp: the item is frozen (kinematic) and re-parented to the TCP. Release: unfrozen and dropped 5 mm above the slot.
- Items are pooled by `ItemFactory` (no allocations in continuous production).
- Sensors are physics queries: light barrier ray, colour ray, Area3D overlaps for grip and fill level.

## Consequences
+ Realistic accumulation and drop behaviour; sensors work on real geometry.
+ Verified: 600 s run, 48 parts, no tipping, no tracking faults, stop accuracy ±10 mm.
− Not bit-exact deterministic across platforms. Fallback (not needed so far): a kinematic transport view behind the
  same conveyor model.
