# Device: qa_station

Quality assurance station with a true-colour sensor (CIELAB comparison against a taught colour) and a ring light.
The sensor is mounted at an angle on the +Z side of the belt so the space above the part stays free for the robot gripper.

| Part | File |
|---|---|
| Behaviour (FMU) | `model/qa_station_model.gd` + `model/modelDescription.xml`, colour maths in `model/color_math.gd` |
| Physical stimulus | `probes/color_probe.gd`: ray from the sensor head to the part top; surface colour via `TrackedItem.get_surface_color_at()` |
| View | `view/qa_station_greybox_view.gd`: bracket, sensor, ring light, result lamp, `PickPoint` marker (robot teach point) |
| Shared geometry | `model/qa_station_geometry.gd` |

Geometry options: `part_height` (0.235 m), `sensor_height` above the part top (0.09), `sensor_offset` in +Z (0.12),
`pick_height` of the robot grip point above the belt (0.15).

Measurement: a rising `trigger` edge starts integration (`integration_time`). Then `r,g,b,hue,delta_e,result_ok` are
latched and `result_valid` stays true while `trigger` is held.
`result_ok = object_present AND deltaE76(measured, taught) <= tolerance_delta_e`.
Fault injection (tunable parameters, default 0): `contamination` 0..1 fades the perceived colour towards dark grey
before the noise (dirty lens: ΔE rises, false rejects from ≈ 0.35), `drift` adds an offset to all channels. See
docs/interfaces/scenarios.md.
