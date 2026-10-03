extends GutTest

const Model := preload("res://devices/conveyor/model/conveyor_model.gd")
const MD := "res://devices/conveyor/model/modelDescription.xml"
const H := 1.0 / 60.0


func _make() -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("CV", Fmi3ModelDescription.load_file(MD))
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	return m


func _steps(m: Fmi3CoSimulation, n: int) -> void:
	for i in n:
		m.do_step(m.current_time, H)


func test_ramps_to_setpoint_and_travels() -> void:
	var m := _make()
	m.set_value("run", true)
	_steps(m, 10)  # 0.167 s * 0.8 m/s² = 0.133 m/s
	assert_almost_eq(m.get_value("belt_speed"), 0.1333, 0.002)
	_steps(m, 110)
	assert_almost_eq(m.get_value("belt_speed"), 0.25, 1e-6)
	assert_true(m.get_value("running"))
	assert_gt(m.get_value("belt_position"), 0.4)


func test_stop_ramp_and_power() -> void:
	var m := _make()
	m.set_value("run", true)
	_steps(m, 60)
	assert_almost_eq(m.get_value("power"), 8.0 + 35.0 + 120.0 * 0.25, 1e-6)
	m.set_value("run", false)
	_steps(m, 30)
	assert_almost_eq(m.get_value("belt_speed"), 0.0, 1e-9)
	assert_false(m.get_value("running"))
	assert_almost_eq(m.get_value("power"), 8.0, 1e-9)


func test_setpoint_is_clamped_and_reversible() -> void:
	var m := _make()
	m.set_value("run", true)
	m.set_value("reverse", true)
	m.set_value("speed_setpoint", 2.0)
	_steps(m, 120)
	assert_almost_eq(m.get_value("belt_speed"), -0.5, 1e-6)
