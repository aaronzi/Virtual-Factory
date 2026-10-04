# Device: conveyor

Flat belt conveyor (aluminium profile frame, gear motor with VFD, side guides).

| Part | File |
|---|---|
| Behaviour (FMU) | `model/conveyor_model.gd` + `model/modelDescription.xml` |
| View + physical actuation | `view/conveyor_greybox_view.gd`: belt `StaticBody3D.constant_linear_velocity` carries items. Belt texture scroll (`view/belt.gdshader`), roller rotation |

Geometry options: `length` (3.0 m), `width` (0.3 m), `height` floor → belt top (0.85 m), `guide_gap` between side guides
(0.08 m).
The device origin is the belt top surface centre. Local +X is the transport direction.

Key variables: inputs `run`, `reverse`, `speed_setpoint`, `motor_fault` (fault injection); outputs `belt_speed`,
`belt_position`, `running`, `fault`, `power`, `energy`, `operating_hours`.
Motor fault: the drive trips, the belt coasts down (`coast_deceleration`), power drops to standby, `fault` is set until
cleared.
Power model: standby + (no-load + k·|v|) while running.
