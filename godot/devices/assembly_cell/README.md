# Device: assembly_cell (black box)

An enclosed cell that assembles and tests ISO 15552 cylinders (process steps 10–70 of the recipe) and releases
them onto the conveyor infeed. It is a deliberate **black box**: only its interface (FMU variables, MQTT topics
later) and its AAS are visible.

| Part | File |
|---|---|
| Behaviour (FMU) | `model/assembly_cell_model.gd` + `model/modelDescription.xml` |
| Physical actuator | `view/item_spawner.gd`: spawns a workpiece at the `Outlet` marker on each release, via the injected `item_factory` service |
| View | `view/assembly_cell_greybox_view.gd`: housing, window, outlet tunnel, HMI, stack light, progress bar |

Geometry options: `size` (Vector3, 1.6 × 2.0 × 1.2 m), `outlet` (local spawn position, default `(0.95, 0.853, 0)`).

Behaviour: when `enable` is true it assembles for `takt_time`, then releases if `infeed_free`, otherwise it is BLOCKED.
Each release sets `release_count`, `last_serial` (`PC3280-YYYY-NNNNNN`), `last_cap_variant` (from the seeded defect rates), and the
test results `last_leak_rate` and `last_stroke_time`, and `last_lots` - the component lots built into the part
(`model/component_lots.gd`: one feeder per BoM node, each changes its lot after its own number of parts; supplier lot
formats; reported with `part_released` for the as-built BoM of the item passport, ADR-0021). Power = idle + (working + compressed-air equivalent) while assembling.
