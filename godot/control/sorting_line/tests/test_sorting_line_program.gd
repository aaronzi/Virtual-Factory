extends GutTest

const Program := preload("res://control/sorting_line/sorting_line_program.gd")
const MD := "res://control/sorting_line/modelDescription.xml"
const H := 0.01

var plc: Fmi3CoSimulation


func before_each() -> void:
	plc = Program.new()
	plc.instantiate("PLC01", Fmi3ModelDescription.load_file(MD))
	plc.set_value("klt_capacity", 2)
	plc.enter_initialization_mode()
	plc.exit_initialization_mode()


func _run(seconds: float) -> void:
	for i in roundi(seconds / H):
		plc.do_step(plc.current_time, H)


func _part_through(ok: bool, serial: String) -> void:
	plc.set_value("ac_release_count", plc.get_value("ac_release_count") + 1)
	plc.set_value("ac_last_serial", serial)
	_run(0.05)
	assert_false(plc.get_value("ac_infeed_free"), "infeed occupied after release")
	plc.set_value("lb01_signal", true)
	_run(0.2)
	plc.set_value("lb01_signal", false)
	_run(0.05)
	assert_true(plc.get_value("ac_infeed_free"))
	plc.set_value("lb02_signal", true)
	_run(0.1)
	assert_true(plc.get_value("cv_run"), "belt runs during stop delay")
	_run(0.6)
	assert_false(plc.get_value("cv_run"), "belt stopped at station")
	assert_true(plc.get_value("qs_trigger"))
	plc.set_value("qs_result_ok", ok)
	plc.set_value("qs_result_valid", true)
	_run(0.05)
	plc.set_value("qs_result_valid", false)
	assert_false(plc.get_value("qs_trigger"))
	assert_eq(plc.get_value("serial_at_qs"), serial)


func _robot_cycle() -> void:
	assert_true(plc.get_value("rb_job_start"))
	plc.set_value("rb_part_clear", true)
	plc.set_value("lb02_signal", false)
	_run(0.05)
	assert_true(plc.get_value("cv_run"), "belt restarts once the part is clear")
	plc.set_value("rb_job_done", true)
	_run(0.05)
	assert_false(plc.get_value("rb_job_start"), "acknowledged")
	plc.set_value("rb_job_done", false)
	plc.set_value("rb_part_clear", false)
	_run(0.05)


func test_auto_start_reaches_execute() -> void:
	_run(0.1)
	assert_eq(plc.get_value("packml_state"), PackMLStateMachine.State.EXECUTE)
	assert_true(plc.get_value("ac_enable"))
	assert_true(plc.get_value("light_green"))


func test_ok_and_nok_parts_are_sorted() -> void:
	_run(0.1)
	_part_through(true, "S1")
	assert_eq(plc.get_value("rb_place_target"), 1)
	assert_eq(plc.get_value("rb_place_slot"), 0)
	_robot_cycle()
	_part_through(false, "S2")
	assert_eq(plc.get_value("rb_place_target"), 2)
	_robot_cycle()
	_part_through(true, "S3")
	assert_eq(plc.get_value("rb_place_slot"), 1)
	assert_eq([plc.get_value("parts_total"), plc.get_value("parts_ok"), plc.get_value("parts_nok")], [3, 2, 1])


func test_full_klt_suspends_until_exchanged() -> void:
	plc.set_value("auto_exchange", false)
	_run(0.1)
	for i in 2:
		_part_through(true, "S%d" % i)
		_robot_cycle()
	plc.set_value("klt_a_count", 2)
	_part_through(true, "S9")
	_run(0.1)
	assert_eq(plc.get_value("packml_state"), PackMLStateMachine.State.SUSPENDED)
	assert_true(plc.get_value("light_amber"))
	assert_false(plc.get_value("rb_job_start"))
	plc.set_value("auto_exchange", true)
	_run(4.1)
	assert_true(plc.get_value("klt_a_exchange"))
	plc.set_value("klt_a_count", 0)
	_run(0.1)
	assert_eq(plc.get_value("packml_state"), PackMLStateMachine.State.EXECUTE)
	assert_true(plc.get_value("rb_job_start"))
	assert_eq(plc.get_value("rb_place_slot"), 0)


func test_hold_command_stops_production() -> void:
	_run(0.1)
	plc.set_value("packml_command", PackMLStateMachine.Command.HOLD)
	_run(0.05)
	assert_eq(plc.get_value("packml_state"), PackMLStateMachine.State.HELD)
	assert_false(plc.get_value("ac_enable"))
	assert_false(plc.get_value("cv_run"))
	plc.set_value("packml_command", PackMLStateMachine.Command.UNHOLD)
	_run(0.05)
	assert_eq(plc.get_value("packml_state"), PackMLStateMachine.State.EXECUTE)
