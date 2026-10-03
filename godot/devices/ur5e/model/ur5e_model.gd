extends Fmi3CoSimulation
## UR5e robot with 2-finger gripper. Job handshake with the PLC:
##   job_start ↑ (not busy) -> busy, program runs -> job_done (busy false) -> job_start ↓ -> job_done ↓
## Taught positions (home, pick, palletizing corners of KLT A/B) are parameters in the robot base frame.
## Gripper finger wear (Ur5eGripperWear): grows per grip at finger_wear_rate; symptoms finger_wear,
## grip_force, grip_close_time, grasp_retries; a part that slips on every regrip sets gripper_fault (and
## fault) until a retry holds. A rising edge of gripper_maintenance_reset = finger change (wear and counters
## back to 0).

var _q := PackedFloat64Array([0, 0, 0, 0, 0, 0])
var _home_q := PackedFloat64Array()
var _gripper_width := 0.085
var _program: Ur5ePickPlaceProgram = null
var _last_job_start := false
var _meter := EnergyMeter.new()
var _wear := Ur5eGripperWear.new()
var _last_reset := false


func _on_initialize() -> void:
	_gripper_width = _get_var("gripper_open_width")
	_wear = Ur5eGripperWear.new(_get_var("seed"), _get_var("finger_wear_start"), _get_var("grip_force_nominal"))
	_wear.limit = _get_var("finger_wear_limit")
	var home := Ur5eLinearMotion.flange_pose(_vec("home"), tool_basis(), _get_var("tool_length"))
	_home_q = UrKinematics.inverse_preferred(home)
	if _home_q.is_empty():
		_log("home position unreachable")
		_set_var("fault", true)
		_home_q = PackedFloat64Array([0, -PI / 2, PI / 2, -PI / 2, -PI / 2, 0])
	_q = _home_q.duplicate()
	_write_pose_outputs()
	_write_wear_outputs()


func _on_step(_t: float, h: float) -> int:
	var job_start: bool = _get_var("job_start")
	if job_start and not _last_job_start and _program == null and not _get_var("job_done"):
		_start_job()
	if not job_start and _get_var("job_done"):
		_set_var("job_done", false)
		_set_var("part_clear", false)
	_last_job_start = job_start
	var stopped: bool = _get_var("protective_stop")
	_set_var("protective_stopped", stopped)
	_update_wear_inputs()
	var q_before := _q.duplicate()
	if _program != null and not stopped:
		_run_program(h)
	_write_pose_outputs()
	_write_wear_outputs()
	_update_power(q_before, h)
	return Fmi3.Status.OK


func tool_basis() -> Basis:
	return Basis(Vector3.BACK, _get_var("tool_rz")) * Basis(Vector3.RIGHT, PI)


func _start_job() -> void:
	var cfg := {
		"tool_basis": tool_basis(), "tool_length": _get_var("tool_length"),
		"joint_speed": _get_var("joint_speed"), "joint_accel": _get_var("joint_accel"),
		"linear_speed": _get_var("linear_speed"), "linear_accel": _get_var("linear_accel"),
		"gripper_open_width": _get_var("gripper_open_width"), "gripper_speed": _get_var("gripper_speed"),
		"pick_approach": _get_var("pick_approach"), "place_approach": _get_var("place_approach"),
		"home_q": _home_q, "wear": _wear, "regrip_attempts": _get_var("regrip_attempts"),
		"grip_retry_interval": _get_var("grip_retry_interval"),
	}
	var target := "a" if _get_var("place_target") == 1 else "b"
	var place := slot_position(target, _get_var("place_slot"))
	_program = Ur5ePickPlaceProgram.new(_q, _gripper_width, _vec("pick"), place, cfg)
	_set_var("busy", true)
	_set_var("fault", false)


func _run_program(h: float) -> void:
	_program.advance(h, clampf(_get_var("speed_override"), 0.0, 1.0),
		_get_var("object_in_grip"), _get_var("object_width"))
	_q = _program.q
	_gripper_width = _program.gripper_width
	_set_var("part_clear", _program.part_clear)
	_set_var("grasp_ok", _program.grasp_ok)
	_set_var("gripper_closed", _program.step_index >= 2 and _program.step_index <= 5 and not _program.finished)
	_set_var("program_step", _program.step_index + 1)
	_set_var("grip_close_time", _program.close_time)
	_set_var("gripper_fault", _program.grip_fault)
	_set_var("fault", _program.fault or _program.grip_fault)
	if _program.fault:
		_set_var("fault", true)
		_finish_job()
	elif _program.finished:
		_set_var("cycle_count", _get_var("cycle_count") + 1)
		_finish_job()


func _finish_job() -> void:
	_set_var("gripper_fault", false)
	_program = null
	_set_var("busy", false)
	_set_var("job_done", true)
	_set_var("program_step", 0)
	_set_var("gripper_closed", false)


## TCP position of a slot from the palletizing corners (origin, end of row, end of column).
func slot_position(container: String, slot: int) -> Vector3:
	var cols: int = maxi(_get_var("slots_per_row"), 1)
	var rows: int = maxi(_get_var("slot_rows"), 1)
	var col := slot % cols
	var row := mini(slot / cols, rows - 1)
	var origin := _vec("place_" + container)
	var along_row := _vec("place_%s_row" % container) - origin
	var along_col := _vec("place_%s_col" % container) - origin
	var p := origin
	if cols > 1:
		p += along_row * (float(col) / (cols - 1))
	if rows > 1:
		p += along_col * (float(row) / (rows - 1))
	return p


func _write_pose_outputs() -> void:
	for i in 6:
		_set_var("q%d" % (i + 1), _q[i])
	var flange := UrKinematics.forward(_q)
	var tcp: Vector3 = flange.origin + flange.basis.z * _get_var("tool_length")
	_set_var("tcp_x", tcp.x)
	_set_var("tcp_y", tcp.y)
	_set_var("tcp_z", tcp.z)
	_set_var("gripper_width", _gripper_width)


func _update_power(q_before: PackedFloat64Array, h: float) -> void:
	var joint_speed_sum := 0.0
	for i in 6:
		joint_speed_sum += absf(_q[i] - q_before[i]) / h
	var power: float = _get_var("idle_power") + _get_var("motion_power_coefficient") * joint_speed_sum
	_meter.integrate(power, h, _get_var("busy"))
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)


## Tunable wear rate and the finger change (rising edge of gripper_maintenance_reset).
func _update_wear_inputs() -> void:
	_wear.rate = maxf(_get_var("finger_wear_rate"), 0.0)
	var reset: bool = _get_var("gripper_maintenance_reset")
	if reset and not _last_reset:
		_wear.replace_fingers()
		_set_var("grip_close_time", 0.0)
	_last_reset = reset


func _write_wear_outputs() -> void:
	_set_var("grip_cycles", _wear.cycles)
	_set_var("finger_wear", _wear.measured_wear)
	_set_var("grip_force", _wear.force)
	_set_var("grasp_retries", _wear.retries)


func _vec(prefix: String) -> Vector3:
	return Vector3(_get_var(prefix + "_x"), _get_var(prefix + "_y"), _get_var(prefix + "_z"))


func _on_reset() -> void:
	_program = null
	_last_job_start = false
	_last_reset = false
	_meter = EnergyMeter.new()


func _save_internal_state() -> Dictionary:
	# The running program is not snapshotted; snapshots are taken between jobs (documented limitation).
	return {"q": _q, "home_q": _home_q, "gripper": _gripper_width, "last_job_start": _last_job_start,
		"meter": _meter.save(), "wear": _wear.save(), "last_reset": _last_reset}


func _load_internal_state(s: Dictionary) -> void:
	_q = s.get("q", _q)
	_home_q = s.get("home_q", _home_q)
	_gripper_width = s.get("gripper", _gripper_width)
	_last_job_start = s.get("last_job_start", false)
	_meter.load(s.get("meter", {}))
	_wear.load(s.get("wear", {}))
	_last_reset = s.get("last_reset", false)
	_program = null
