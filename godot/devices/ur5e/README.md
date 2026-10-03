# Device: ur5e

Universal Robots UR5e on a pedestal with a generic 2-finger parallel gripper (85 mm stroke).

| Part | File |
|---|---|
| Kinematics | `kinematics/ur_kinematics.gd`: real UR5e DH parameters, FK, closed-form IK (Hawkins 2013, up to 8 solutions), closest/preferred solution |
| Motion | `model/trapezoid_profile.gd`, `model/joint_motion.gd` (movej, synchronised), `model/linear_motion.gd` (movel, IK per sample) |
| Program | `model/pick_place_program.gd`: approach → down → grip → up (part clear) → slot approach → down → release → up → home |
| Behaviour (FMU) | `model/ur5e_model.gd` + `model/modelDescription.xml`: job handshake, palletizing slot grid, protective stop, power model, gripper finger wear |
| Finger wear | `model/gripper_wear.gd`: pad wear per grip (`finger_wear_rate`, limit `finger_wear_limit`), symptoms `finger_wear`, `grip_force`, `grip_close_time`, `grip_cycles`, `grasp_retries`; slip/regrip above 85 % of the limit, `gripper_fault` after `regrip_attempts`; reset by `gripper_maintenance_reset` (ADR-0029) |
| Root | `ur5e_device.gd`: robot base frame (Z-up) at node `Base` on the pedestal; `world_to_device_frame()` for teaching |
| Probe | `probes/grip_probe.gd`: Area3D at the TCP → `object_in_grip`, `object_width` |
| Views | `view/ur5e_greybox_view.gd` (FK-driven links, gripper, TCP node), `view/grasp_actuator.gd` (attach/detach items) |

Geometry options: `pedestal_height` (0.75 m).

Taught parameters (robot base frame, metres): `home_*`, `pick_*`, palletizing corners `place_a_*`, `place_a_row_*`,
`place_a_col_*` (and `_b_`), plus `slots_per_row` × `slot_rows`. The layout's `teach` section sets them from device markers.

Handshake: `job_start ↑` → `busy` → … `part_clear` (part lifted, belt may restart) … → `job_done` until `job_start ↓`.
Power: 90 W powered idle + 45 W per rad/s of summed joint speed (typical 150–350 W while moving).
