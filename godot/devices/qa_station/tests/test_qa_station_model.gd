extends GutTest

const Model := preload("res://devices/qa_station/model/qa_station_model.gd")
const MD := "res://devices/qa_station/model/modelDescription.xml"
const H := 1.0 / 60.0


func _measure(rgb: Color, present := true) -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("QS", Fmi3ModelDescription.load_file(MD))
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	m.set_value("measured_r", rgb.r)
	m.set_value("measured_g", rgb.g)
	m.set_value("measured_b", rgb.b)
	m.set_value("object_present", present)
	m.set_value("trigger", true)
	for i in 6:
		m.do_step(m.current_time, H)
		assert_false(m.get_value("result_valid"), "not valid before integration time")
	for i in 4:
		m.do_step(m.current_time, H)
	assert_true(m.get_value("result_valid"))
	return m


func test_red_cap_is_ok() -> void:
	var m := _measure(Color(0.78, 0.08, 0.10))
	assert_true(m.get_value("result_ok"))
	assert_lt(m.get_value("delta_e"), 5.0)
	assert_eq(m.get_value("measure_count"), 1)


func test_missing_or_wrong_cap_is_nok() -> void:
	assert_false(_measure(Color(0.70, 0.71, 0.72)).get_value("result_ok"), "bare aluminium")
	assert_false(_measure(Color(0.10, 0.30, 0.80)).get_value("result_ok"), "blue cap")
	assert_false(_measure(Color(0.78, 0.08, 0.10), false).get_value("result_ok"), "no object")


func test_result_resets_with_trigger() -> void:
	var m := _measure(Color(0.78, 0.08, 0.10))
	m.set_value("trigger", false)
	m.do_step(m.current_time, H)
	assert_false(m.get_value("result_valid"))
	assert_false(m.get_value("light_on"))


func test_delta_e_reference_values() -> void:
	assert_almost_eq(ColorMath.delta_e76(Vector3.ONE, Vector3.ONE), 0.0, 1e-6)
	assert_almost_eq(ColorMath.srgb_to_lab(Vector3.ONE).x, 100.0, 0.05, "white L* = 100")
	assert_almost_eq(ColorMath.delta_e76(Vector3.ZERO, Vector3.ONE), 100.0, 0.05)
