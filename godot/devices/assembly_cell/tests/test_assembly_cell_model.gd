extends GutTest

const Model := preload("res://devices/assembly_cell/model/assembly_cell_model.gd")
const MD := "res://devices/assembly_cell/model/modelDescription.xml"
const H := 0.1


func _make(params := {}) -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("AC", Fmi3ModelDescription.load_file(MD))
	for k in params:
		m.set_value(k, params[k])
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	return m


func _run(m: Fmi3CoSimulation, seconds: float) -> void:
	for i in roundi(seconds / H):
		m.do_step(m.current_time, H)


func test_releases_at_takt_with_serials() -> void:
	var m := _make({"takt_time": 10.0})
	m.set_value("enable", true)
	m.set_value("infeed_free", true)
	_run(m, 9.9)
	assert_eq(m.get_value("release_count"), 0)
	_run(m, 0.2)
	assert_eq(m.get_value("release_count"), 1)
	assert_eq(m.get_value("last_serial"), "PC3280-2026-000001")
	_run(m, 10.0)
	assert_eq(m.get_value("last_serial"), "PC3280-2026-000002")


func test_blocks_until_infeed_free() -> void:
	var m := _make({"takt_time": 5.0})
	m.set_value("enable", true)
	_run(m, 6.0)
	assert_eq(m.get_value("state"), 2, "blocked")
	assert_eq(m.get_value("release_count"), 0)
	m.set_value("infeed_free", true)
	_run(m, 0.1)
	assert_eq(m.get_value("release_count"), 1)
	assert_eq(m.get_value("state"), 1)


func test_defect_distribution_and_determinism() -> void:
	var m := _make({"takt_time": 1.0, "defect_rate_missing_cap": 0.2, "defect_rate_wrong_cap": 0.1})
	m.set_value("enable", true)
	m.set_value("infeed_free", true)
	var counts := [0, 0, 0]
	for i in 1000:
		_run(m, 1.0)
		counts[m.get_value("last_cap_variant")] += 1
	assert_almost_eq(counts[1] / 1000.0, 0.2, 0.04)
	assert_almost_eq(counts[2] / 1000.0, 0.1, 0.03)
	var again := _make({"takt_time": 1.0, "defect_rate_missing_cap": 0.2, "defect_rate_wrong_cap": 0.1})
	again.set_value("enable", true)
	again.set_value("infeed_free", true)
	_run(again, 1.0)
	var first := _make({"takt_time": 1.0, "defect_rate_missing_cap": 0.2, "defect_rate_wrong_cap": 0.1})
	first.set_value("enable", true)
	first.set_value("infeed_free", true)
	_run(first, 1.0)
	assert_eq(again.get_value("last_leak_rate"), first.get_value("last_leak_rate"), "same seed, same data")


func test_defect_rate_is_tunable_at_runtime() -> void:
	var m := _make({"takt_time": 1.0})
	m.set_value("enable", true)
	m.set_value("infeed_free", true)
	assert_eq(m.set_value("defect_rate_missing_cap", 1.0), Fmi3.Status.OK, "settable in step mode")
	_run(m, 1.05)
	assert_eq(m.get_value("last_cap_variant"), 1, "missing cap after the rate was raised")
	m.set_value("defect_rate_missing_cap", 0.0)
	m.set_value("defect_rate_wrong_cap", 1.0)
	_run(m, 1.0)
	assert_eq(m.get_value("last_cap_variant"), 2, "wrong cap")
