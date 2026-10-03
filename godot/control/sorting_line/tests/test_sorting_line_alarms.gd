extends GutTest
## Alarm reactions of the LINE01 PLC (codes: docs/interfaces/scenarios.md).

const Program := preload("res://control/sorting_line/sorting_line_program.gd")
const MD := "res://control/sorting_line/modelDescription.xml"
const H := 0.01
const S := PackMLStateMachine.State
const C := PackMLStateMachine.Command

var plc: Fmi3CoSimulation


func before_each() -> void:
	plc = Program.new()
	plc.instantiate("PLC01", Fmi3ModelDescription.load_file(MD))
	plc.enter_initialization_mode()
	plc.exit_initialization_mode()
	_run(0.1)


func _run(seconds: float) -> void:
	for i in roundi(seconds / H):
		plc.do_step(plc.current_time, H)


func _command(cmd: int) -> void:
	plc.set_value("packml_command", cmd)
	_run(0.05)
	plc.set_value("packml_command", C.NONE)
	_run(0.05)


func _alarm() -> Array:
	return [plc.get_value("alarm_code"), plc.get_value("packml_state")]


func test_no_alarm_in_normal_operation() -> void:
	assert_eq(_alarm(), [0, S.EXECUTE])
	assert_eq(plc.get_value("alarm_text"), "")
	assert_false(plc.get_value("light_red"))
	assert_false(plc.get_value("horn"))


func test_conveyor_fault_aborts_until_cleared_and_reset() -> void:
	plc.set_value("cv_fault", true)
	_run(0.05)
	assert_eq(_alarm(), [101, S.ABORTED])
	assert_eq(plc.get_value("alarm_text"), "CV01 conveyor drive fault")
	assert_true(plc.get_value("light_red"))
	assert_true(plc.get_value("horn"))
	assert_false(plc.get_value("cv_run"))
	assert_eq(plc.get_value("alarm_count"), 1)
	_command(C.CLEAR)
	assert_eq(_alarm(), [101, S.ABORTED], "cannot clear while the fault is active")
	plc.set_value("cv_fault", false)
	_run(0.05)
	assert_eq(_alarm(), [0, S.ABORTED], "stays aborted after the fault is gone")
	_command(C.CLEAR)
	assert_eq(plc.get_value("packml_state"), S.STOPPED)
	_command(C.RESET)
	_run(0.05)
	assert_eq(plc.get_value("packml_state"), S.EXECUTE, "auto_start after reset")


func test_estop_aborts_and_blocks_clear_until_released() -> void:
	plc.set_value("estop", true)
	plc.set_value("rb_protective_stop", true)  # the safety circuit also stops the robot
	_run(0.05)
	assert_eq(_alarm(), [100, S.ABORTED], "E-stop has the highest priority")
	_command(C.CLEAR)
	assert_eq(_alarm(), [100, S.ABORTED], "cannot clear while the button is latched")
	plc.set_value("estop", false)
	plc.set_value("rb_protective_stop", false)
	_run(0.05)
	_command(C.CLEAR)
	_command(C.RESET)
	_run(0.05)
	assert_eq(_alarm(), [0, S.EXECUTE])


func test_protective_stop_holds_until_released() -> void:
	plc.set_value("rb_protective_stop", true)
	_run(0.05)
	assert_eq(_alarm(), [201, S.HELD])
	assert_false(plc.get_value("ac_enable"))
	assert_true(plc.get_value("light_red"))
	plc.set_value("rb_protective_stop", false)
	_run(0.05)
	assert_eq(_alarm(), [0, S.EXECUTE], "automatic unhold after release")
	assert_true(plc.get_value("light_green"))


func test_manual_hold_is_not_released_by_alarm_logic() -> void:
	_command(C.HOLD)
	plc.set_value("rb_protective_stop", true)
	_run(0.05)
	plc.set_value("rb_protective_stop", false)
	_run(0.05)
	assert_eq(_alarm(), [0, S.HELD], "operator hold stays")


func test_stuck_light_barrier_holds_line() -> void:
	plc.set_value("lb02_signal", true)  # rising edge: a (ghost) part arrives
	plc.set_value("qs_result_valid", true)
	_run(1.0)
	plc.set_value("qs_result_valid", false)
	assert_true(plc.get_value("rb_job_start"))
	plc.set_value("rb_part_clear", true)  # robot "picked" it, but the beam stays blocked
	_run(1.0)
	assert_eq(_alarm(), [0, S.EXECUTE], "within sensor_blocked_timeout")
	assert_true(plc.get_value("cv_run"))
	_run(0.6)
	assert_eq(_alarm(), [302, S.HELD])
	assert_false(plc.get_value("cv_run"))
	plc.set_value("lb02_signal", false)
	_run(0.05)
	assert_eq(_alarm(), [0, S.EXECUTE])


func test_infeed_timeout_is_a_warning() -> void:
	plc.set_value("ac_release_count", 1)
	plc.set_value("ac_last_serial", "S1")
	_run(8.1)
	assert_eq(_alarm(), [401, S.EXECUTE], "warning only")
	assert_eq(plc.get_value("infeed_faults"), 1)
	assert_true(plc.get_value("light_amber"))
	assert_false(plc.get_value("horn"))
	plc.set_value("lb01_signal", true)
	_run(0.1)
	plc.set_value("lb01_signal", false)
	_run(0.05)
	assert_eq(plc.get_value("alarm_code"), 0, "cleared by the next LB01 detection")


func test_robot_fault_holds_on_edge_only() -> void:
	plc.set_value("rb_fault", true)
	_run(0.05)
	assert_eq(_alarm(), [202, S.HELD])
	_command(C.UNHOLD)
	assert_eq(_alarm(), [202, S.EXECUTE], "operator can unhold while the robot reports the fault")


func test_robot_job_finishing_while_aborted_does_not_block_the_sequence() -> void:
	plc.set_value("lb02_signal", true)
	plc.set_value("qs_result_valid", true)
	_run(1.0)
	assert_true(plc.get_value("rb_job_start"), "pick requested")
	plc.set_value("cv_fault", true)
	_run(0.05)
	assert_eq(plc.get_value("packml_state"), S.ABORTED)
	plc.set_value("rb_part_clear", true)  # robot continues its job while the line is aborted
	plc.set_value("lb02_signal", false)
	plc.set_value("qs_result_valid", false)
	plc.set_value("rb_job_done", true)
	_run(0.05)
	plc.set_value("rb_job_done", false)
	plc.set_value("rb_part_clear", false)
	plc.set_value("cv_fault", false)
	_run(0.05)
	_command(C.CLEAR)
	_command(C.RESET)
	_run(0.05)
	assert_eq(plc.get_value("packml_state"), S.EXECUTE)
	assert_eq(plc.get_value("sequence_step"), 0, "back in WAIT_PART")
	assert_true(plc.get_value("cv_run"), "belt runs for the next part")
