extends GutTest

const Model := preload("res://devices/light_barrier/model/light_barrier_model.gd")
const MD := "res://devices/light_barrier/model/modelDescription.xml"
const H := 1.0 / 60.0


func _make(params := {}) -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("LB", Fmi3ModelDescription.load_file(MD))
	for k in params:
		m.set_value(k, params[k])
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	return m


func _run(m: Fmi3CoSimulation, blocked: bool, steps: int) -> void:
	m.set_value("beam_blocked", blocked)
	for i in steps:
		m.do_step(m.current_time, H)


func test_response_time_filters_short_pulses() -> void:
	var m := _make({"response_time": 0.05})
	_run(m, true, 2)  # 33 ms < 50 ms
	_run(m, false, 1)
	assert_false(m.get_value("signal"))
	_run(m, true, 4)  # 66 ms
	assert_true(m.get_value("signal"))
	assert_eq(m.get_value("switch_count"), 1)


func test_light_on_logic_and_energy() -> void:
	var m := _make({"dark_on": false, "response_time": 0.0})
	_run(m, false, 1)
	assert_true(m.get_value("signal"), "light-on: active while beam is free")
	_run(m, false, 3600 * 60 - 1)
	assert_almost_eq(m.get_value("energy"), 1.2 / 1000.0, 1e-6, "1.2 W for 1 h = 1.2 Wh")
	assert_almost_eq(m.get_value("operating_hours"), 1.0, 1e-3)
