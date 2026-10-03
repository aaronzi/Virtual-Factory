extends GutTest

const Model := preload("res://devices/ur5e/model/ur5e_model.gd")
const MD := "res://devices/ur5e/model/modelDescription.xml"
const H := 1.0 / 60.0
const PICK := Vector3(0.0, -0.55, 0.25)


func _make() -> Fmi3CoSimulation:
	var m: Fmi3CoSimulation = Model.new()
	m.instantiate("RB", Fmi3ModelDescription.load_file(MD))
	_set_vec(m, "pick", PICK)
	_set_vec(m, "place_a", Vector3(0.4, 0.18, -0.025))
	_set_vec(m, "place_a_row", Vector3(0.4, -0.18, -0.025))
	_set_vec(m, "place_a_col", Vector3(0.6, 0.18, -0.025))
	_set_vec(m, "place_b", Vector3(-0.6, 0.18, -0.025))
	_set_vec(m, "place_b_row", Vector3(-0.6, -0.18, -0.025))
	_set_vec(m, "place_b_col", Vector3(-0.4, 0.18, -0.025))
	m.enter_initialization_mode()
	m.exit_initialization_mode()
	return m


func _set_vec(m: Fmi3CoSimulation, prefix: String, v: Vector3) -> void:
	m.set_value(prefix + "_x", v.x)
	m.set_value(prefix + "_y", v.y)
	m.set_value(prefix + "_z", v.z)


func _tcp(m: Fmi3CoSimulation) -> Vector3:
	return Vector3(m.get_value("tcp_x"), m.get_value("tcp_y"), m.get_value("tcp_z"))


func test_home_pose_is_reached_at_start() -> void:
	var m := _make()
	assert_false(m.get_value("fault"))
	assert_almost_eq(_tcp(m).distance_to(Vector3(0.0, -0.30, 0.45)), 0.0, 1e-3)


func test_slot_grid_from_palletizing_corners() -> void:
	var m := _make()
	assert_almost_eq(m.slot_position("a", 0).distance_to(Vector3(0.4, 0.18, -0.025)), 0.0, 1e-6)
	assert_almost_eq(m.slot_position("a", 3).distance_to(Vector3(0.4, -0.18, -0.025)), 0.0, 1e-6)
	assert_almost_eq(m.slot_position("a", 11).distance_to(Vector3(0.6, -0.18, -0.025)), 0.0, 1e-6)
	assert_almost_eq(m.slot_position("a", 5).distance_to(Vector3(0.5, 0.06, -0.025)), 0.0, 1e-6)


func test_full_pick_place_job() -> void:
	var m := _make()
	m.set_value("object_in_grip", true)
	m.set_value("object_width", 0.047)
	m.set_value("place_target", 2)
	m.set_value("place_slot", 5)
	m.set_value("job_start", true)
	var min_pick := INF
	var min_place := INF
	var clear_time := -1.0
	var place: Vector3 = m.slot_position("b", 5)
	var t := 0.0
	while t < 20.0 and not m.get_value("job_done"):
		m.do_step(t, H)
		t += H
		min_pick = minf(min_pick, _tcp(m).distance_to(PICK))
		min_place = minf(min_place, _tcp(m).distance_to(place))
		if clear_time < 0.0 and m.get_value("part_clear"):
			clear_time = t
	assert_true(m.get_value("job_done"), "job finished")
	assert_false(m.get_value("fault"))
	assert_between(t, 4.0, 11.0, "realistic cycle time (s)")
	assert_between(clear_time, 1.0, 4.0, "part cleared from the belt early")
	assert_lt(min_pick, 2e-3, "TCP reached pick position")
	assert_lt(min_place, 2e-3, "TCP reached slot position")
	assert_eq(m.get_value("cycle_count"), 1)
	assert_almost_eq(_tcp(m).distance_to(Vector3(0.0, -0.30, 0.45)), 0.0, 2e-3, "back home")
	m.set_value("job_start", false)
	m.do_step(t, H)
	assert_false(m.get_value("job_done"), "handshake reset")


func test_protective_stop_freezes_motion() -> void:
	var m := _make()
	m.set_value("job_start", true)
	for i in 30:
		m.do_step(i * H, H)
	m.set_value("protective_stop", true)
	var before := _tcp(m)
	for i in 30:
		m.do_step((30 + i) * H, H)
	assert_almost_eq(_tcp(m).distance_to(before), 0.0, 1e-9)
	assert_true(m.get_value("busy"))
