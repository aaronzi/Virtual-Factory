# Device: light_barrier

Retro-reflective photoelectric sensor (emitter/receiver housing on one side, reflector on the other).

| Part | File |
|---|---|
| Behaviour (FMU) | `model/light_barrier_model.gd` + `model/modelDescription.xml` |
| Physical stimulus | `probes/beam_probe.gd`: ray emitter → reflector against `PhysicsLayers.ITEMS` |
| View | `view/light_barrier_greybox_view.gd`: housing, reflector, power LED (green), signal LED (yellow) |

Geometry options (layout `geometry`): `beam_length` (m, default 0.44), `beam_height` above the device origin (m, default 0.05).
The device origin sits on the belt surface, at the centreline, at the beam position. The beam runs along local Z.

Key variables: input `beam_blocked`; parameters `response_time`, `dark_on`, `rated_power`; outputs `signal`, `switch_count`, `power`, `energy`, `operating_hours`.
