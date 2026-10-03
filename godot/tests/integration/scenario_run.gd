extends SceneTree
## Headless run of the line with a training scenario, checks the expected effect in the PLC:
##   godot --headless --fixed-fps 60 -s res://tests/integration/scenario_run.gd -- \
##     --vf-scenario=<id> --vf-sim-seconds=240 --vf-uns=off
## (the factory starts the scenario from --vf-scenario). Exits with code 1 if the effect is missing.

const MAIN := "res://factory/main.tscn"
const EXECUTE := 6
const HELD := 11
const ABORTED := 9
## Expected effect per scenario: minimum NOK parts, alarm codes and PackML states that must occur,
## and whether the line must be back in EXECUTE at the end.
const EXPECT := {
	"missing_cap_burst": {"min_nok": 5, "alarms": [], "states": [], "recovers": true},
	"dirty_color_sensor": {"min_nok": 3, "alarms": [], "states": [], "recovers": true},
	"light_barrier_misalignment": {"min_nok": 1, "alarms": [302], "states": [HELD], "recovers": true},
	"conveyor_motor_fault": {"min_nok": 0, "alarms": [101], "states": [ABORTED], "recovers": true,
		"min_inspected": 12},
	"robot_protective_stop": {"min_nok": 0, "alarms": [201], "states": [HELD], "recovers": true},
	"gripper_wear": {"min_nok": 0, "alarms": [], "states": [], "recovers": true, "min_finger_wear": 4e-4},
}

var _alarms := {}
var _states := {}
var _max_delta_e := 0.0
var _history: Array[String] = []  # "t:code" on every alarm_code change
var _last_code := 0


func _initialize() -> void:
	var seconds := 240.0
	var id := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--vf-sim-seconds="):
			seconds = arg.get_slice("=", 1).to_float()
		elif arg.begins_with("--vf-scenario="):
			id = arg.get_slice("=", 1)
	var main: Node = load(MAIN).instantiate()
	root.add_child(main)
	var factory: Node = main.get_node("Factory")
	for i in roundi(seconds * 60.0):
		await physics_frame
		_record(factory)
	quit(_check(factory, id, seconds))


func _record(f: Node) -> void:
	var code: int = f.read("PLC01.alarm_code")
	if code != _last_code:
		_history.append("%.1f:%d" % [f.builder.master.time, code])
		_last_code = code
	_alarms[code] = true
	_states[f.read("PLC01.packml_state")] = true
	_max_delta_e = maxf(_max_delta_e, f.read("QS01.delta_e"))


func _check(f: Node, id: String, seconds: float) -> int:
	var runner: ScenarioRunner = f.scenarios
	var report := {
		"scenario": id, "sim_seconds": seconds, "steps_fired": runner.step_index + 1,
		"inspected": f.read("PLC01.parts_total"), "ok": f.read("PLC01.parts_ok"),
		"nok": f.read("PLC01.parts_nok"), "alarms_seen": _alarms.keys(), "states_seen": _states.keys(),
		"alarm_count": f.read("PLC01.alarm_count"), "final_state": f.read("PLC01.packml_state"),
		"max_delta_e": snappedf(_max_delta_e, 0.1), "lb02_switches": f.read("LB02.switch_count"),
		"stack_light": [f.read("SL01.green_on"), f.read("SL01.amber_on"), f.read("SL01.red_on")],
		"alarm_history": _history, "finger_wear_mm": snappedf(f.read("RB01.finger_wear") * 1000.0, 0.001),
		"grip_force": snappedf(f.read("RB01.grip_force"), 0.1), "grasp_retries": f.read("RB01.grasp_retries"),
	}
	print("SCENARIO RUN REPORT ", JSON.stringify(report))
	var problems := _problems(runner, id, report)
	for p in problems:
		printerr("SCENARIO RUN FAILED: ", p)
	return 1 if problems.size() > 0 else 0


func _problems(runner: ScenarioRunner, id: String, report: Dictionary) -> Array[String]:
	var problems: Array[String] = []
	var expect: Dictionary = EXPECT.get(id, {})
	if expect.is_empty():
		return ["no expectation for scenario '%s'" % id]
	if runner.active or runner.step_index + 1 != runner.get_scenario(id).steps.size():
		problems.append("scenario did not complete")
	if report.inspected < expect.get("min_inspected", 10):
		problems.append("production did not continue (%d inspected)" % report.inspected)
	if report.nok < expect.min_nok:
		problems.append("expected at least %d NOK parts" % expect.min_nok)
	for code: int in expect.alarms:
		if not _alarms.has(code):
			problems.append("alarm %d not raised" % code)
	for state: int in expect.states:
		if not _states.has(state):
			problems.append("PackML state %d not reached" % state)
	if report.finger_wear_mm < expect.get("min_finger_wear", 0.0) * 1000.0:
		problems.append("finger wear did not reach %.2f mm" % (expect.min_finger_wear * 1000.0))
	if expect.recovers and report.final_state != EXECUTE:
		problems.append("line did not return to EXECUTE")
	return problems
