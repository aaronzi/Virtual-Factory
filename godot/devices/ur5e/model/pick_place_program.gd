class_name Ur5ePickPlaceProgram
extends RefCounted
## URScript-like pick & place job, executed step by step:
##   movej above pick -> movel down -> grip -> movel up (part clear) -> movej above slot
##   -> movel down -> release -> movel up -> movej home.
## Grip with finger wear (cfg.wear, Ur5eGripperWear): worn jaws close slower and further; a slipped part is
## regripped (reopen, close again) up to cfg.regrip_attempts times, then `grip_fault` is set and the grip is
## retried every cfg.grip_retry_interval seconds until it holds (e.g. after a finger change).

const REGRIP_OPEN := 0.01  ## m the jaws reopen for a regrip

var q: PackedFloat64Array
var gripper_width := 0.0
var step_index := 0
var finished := false
var fault := false
var part_clear := false
var grasp_ok := false
var grip_fault := false  ## every regrip attempt slipped; waiting for the next retry
var close_time := 0.0  ## duration of the last closing movement of the jaws [s]
var _steps: Array[Dictionary] = []
var _motion: RefCounted = null
var _t := 0.0
var _cfg := {}
var _attempts := 0
var _reopen := false
var _close_t := 0.0
var _retry_wait := 0.0


## cfg keys: tool_basis, tool_length, joint_speed, joint_accel, linear_speed, linear_accel,
## gripper_open_width, gripper_speed, pick_approach, place_approach, home_q; optional: wear,
## regrip_attempts, grip_retry_interval.
func _init(start_q: PackedFloat64Array, start_width: float, pick: Vector3, place: Vector3,
		cfg: Dictionary) -> void:
	q = start_q
	gripper_width = start_width
	_cfg = cfg
	var up_pick := pick + Vector3(0, 0, cfg.pick_approach)
	var up_place := place + Vector3(0, 0, cfg.place_approach)
	_steps = [
		{"op": "movej", "tcp": up_pick}, {"op": "movel", "tcp": pick}, {"op": "grip"},
		{"op": "movel", "tcp": up_pick, "clear": true}, {"op": "movej", "tcp": up_place},
		{"op": "movel", "tcp": place}, {"op": "release"}, {"op": "movel", "tcp": up_place},
		{"op": "movej", "q": cfg.home_q},
	]


## Advances the program by h seconds. `speed` is the speed override (0..1).
func advance(h: float, speed: float, object_in_grip: bool, object_width: float) -> void:
	var remaining := h
	while remaining > 1e-9 and not finished and not fault:
		var step := _steps[step_index]
		if step.op in ["grip", "release"]:
			remaining = _advance_gripper(step.op, remaining, speed, object_in_grip, object_width)
		else:
			remaining = _advance_motion(step, remaining, speed)


func _advance_motion(step: Dictionary, h: float, speed: float) -> float:
	if _motion == null:
		_motion = _create_motion(step, speed)
		_t = 0.0
		if _motion == null:
			fault = true
			return 0.0
	_t += h
	var new_q: PackedFloat64Array = _motion.sample(minf(_t, _motion.duration), q)
	if new_q.is_empty():
		fault = true
		return 0.0
	q = new_q
	if _t < _motion.duration:
		return 0.0
	part_clear = part_clear or step.get("clear", false)
	_next_step()
	return _t - _motion_duration_done()


func _advance_gripper(op: String, h: float, speed: float, present: bool, width: float) -> float:
	if op == "grip" and grip_fault:
		return _wait_for_retry(h)
	var wear: Ur5eGripperWear = _cfg.get("wear")
	var target: float = _cfg.gripper_open_width
	if op == "grip":
		target = _grip_target(present, width, wear)
	var rate: float = _cfg.gripper_speed * maxf(speed, 0.05) * (wear.speed_factor() if wear else 1.0)
	var needed := absf(target - gripper_width) / rate
	gripper_width = move_toward(gripper_width, target, rate * h)
	var closing := op == "grip" and not _reopen
	if needed > h:
		_close_t += h if closing else 0.0
		return 0.0
	if op == "release":
		grasp_ok = false
		_next_step()
		return h - needed
	if _reopen:
		_reopen = false
		return h - needed
	close_time = _close_t + needed
	_close_t = 0.0
	return _evaluate_grip(h - needed, present, wear)


func _grip_target(present: bool, width: float, wear: Ur5eGripperWear) -> float:
	var open_width: float = _cfg.gripper_open_width
	if not present:
		return 0.0
	if _reopen:
		return minf(width + REGRIP_OPEN, open_width)
	var offset := 2.0 * wear.contact_offset() if wear else 0.0
	return clampf(width - offset, 0.0, open_width)


## Jaws closed on the part: held -> next step; slipped -> regrip or, after the last attempt, grip fault.
func _evaluate_grip(remaining: float, present: bool, wear: Ur5eGripperWear) -> float:
	if not present or wear == null or wear.grip():
		grasp_ok = present
		_attempts = 0
		_next_step()
		return remaining
	_attempts += 1
	if _attempts < int(_cfg.get("regrip_attempts", 3)):
		_reopen = true
		return remaining
	grip_fault = true
	_retry_wait = _cfg.get("grip_retry_interval", 10.0)
	return 0.0


func _wait_for_retry(h: float) -> float:
	_retry_wait -= h
	if _retry_wait <= 0.0:
		grip_fault = false
		_attempts = 0
		_reopen = true
	return 0.0


func _create_motion(step: Dictionary, speed: float) -> RefCounted:
	var s := maxf(speed, 0.05)
	if step.op == "movel":
		var start := current_tcp()
		return Ur5eLinearMotion.new(start, step.tcp, _cfg.tool_basis, _cfg.tool_length,
			_cfg.linear_speed * s, _cfg.linear_accel * s)
	var goal: PackedFloat64Array = step.get("q", PackedFloat64Array())
	if goal.is_empty():
		goal = UrKinematics.inverse_closest(
			Ur5eLinearMotion.flange_pose(step.tcp, _cfg.tool_basis, _cfg.tool_length), q)
		if goal.is_empty():
			return null
	return Ur5eJointMotion.new(q, goal, _cfg.joint_speed * s, _cfg.joint_accel * s)


func current_tcp() -> Vector3:
	var flange := UrKinematics.forward(q)
	var tool_length: float = _cfg.tool_length
	return flange.origin + flange.basis.z * tool_length


func _next_step() -> void:
	step_index += 1
	if step_index >= _steps.size():
		finished = true
		step_index = _steps.size() - 1


func _motion_duration_done() -> float:
	var d: float = _motion.duration
	_motion = null
	return d
