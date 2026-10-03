extends GutTest

const Model := preload("res://devices/stack_light/model/stack_light_model.gd")
const MD := "res://devices/stack_light/model/modelDescription.xml"
const H := 1.0 / 60.0


func _make() -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("SL", Fmi3ModelDescription.load_file(MD))
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	return m


func test_segments_follow_inputs_and_power() -> void:
	var m := _make()
	m.do_step(0.0, H)
	assert_almost_eq(m.get_value("power"), 0.2, 1e-9, "standby")
	m.set_value("green", true)
	m.do_step(H, H)
	assert_true(m.get_value("green_on"))
	assert_false(m.get_value("red_on"))
	assert_almost_eq(m.get_value("power"), 2.0, 1e-9)
	m.set_value("green", false)
	m.set_value("red", true)
	m.set_value("amber", true)
	m.set_value("buzzer", true)
	m.do_step(2 * H, H)
	assert_eq([m.get_value("green_on"), m.get_value("amber_on"), m.get_value("red_on"),
		m.get_value("buzzer_on")], [false, true, true, true])
	assert_almost_eq(m.get_value("power"), 0.2 + 2 * 1.8 + 0.8, 1e-9)
