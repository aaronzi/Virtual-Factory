# Device: light_barrier

Retro-reflective photoelectric sensor (emitter/receiver housing on one side, reflector on the other).

| Part | File |
|---|---|
| Behaviour (FMU) | `model/light_barrier_model.gd` + `model/modelDescription.xml` |
| Physical stimulus | `probes/beam_probe.gd`: ray emitter → reflector against `PhysicsLayers.ITEMS` |
| View | `view/light_barrier_greybox_view.gd`: housing, reflector, power LED (green), signal LED (yellow) |

Geometry options (layout `geometry`): `beam_length` (m, default 0.44), `beam_height` above the device origin (m, default
0.05).
The device origin sits on the belt surface, at the centreline, at the beam position. The beam runs along local Z.

Key variables: inputs `beam_blocked`, `misalignment` (fault injection 0..1); parameters `response_time`, `dark_on`,
`rated_power`, `seed`, `dropout_rate`, `dropout_duration`; outputs `signal`, `switch_count`, `stability_ok`, `power`,
`energy`, `operating_hours`.
Misalignment: random beam dropouts (rate ∝ value, seeded) → false triggers; at 1 the beam is lost (signal stuck). See docs/interfaces/scenarios.md.
