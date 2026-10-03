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


func _count_activations(m: Fmi3CoSimulation, seconds: float) -> int:
	var before: int = m.get_value("switch_count")
	_run(m, false, roundi(seconds / H))
	return m.get_value("switch_count") - before


func test_misalignment_causes_false_triggers_proportionally() -> void:
	var clean := _make()
	assert_eq(_count_activations(clean, 60.0), 0, "aligned: no false triggers")
	assert_true(clean.get_value("stability_ok"))
	var slight := _make()
	slight.set_value("misalignment", 0.2)
	var strong := _make()
	strong.set_value("misalignment", 0.8)
	var n_slight := _count_activations(slight, 60.0)
	var n_strong := _count_activations(strong, 60.0)
	assert_gt(n_slight, 5, "0.2 * 1.5/s * 60 s = 18 expected")
	assert_gt(n_strong, n_slight * 2, "rate grows with misalignment")
	assert_false(strong.get_value("stability_ok"))


func test_misalignment_is_deterministic_with_seed() -> void:
	var a := _make()
	var b := _make()
	a.set_value("misalignment", 0.5)
	b.set_value("misalignment", 0.5)
	assert_eq(_count_activations(a, 30.0), _count_activations(b, 30.0))


func test_full_misalignment_blocks_the_beam_permanently() -> void:
	var m := _make()
	m.set_value("misalignment", 1.0)
	_run(m, false, 120)
	assert_true(m.get_value("signal"), "signal stuck")
	assert_eq(m.get_value("switch_count"), 1)
	m.set_value("misalignment", 0.0)
	_run(m, false, 2)
	assert_false(m.get_value("signal"), "recovers after realignment")
