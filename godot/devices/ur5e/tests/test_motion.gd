extends GutTest


func test_trapezoid_profile() -> void:
	var p := TrapezoidProfile.new(1.0, 0.5, 1.0)  # ta = 0.5 s, cruise 1.5 s
	assert_almost_eq(p.duration, 2.5, 1e-9)
	assert_almost_eq(p.fraction(0.5), 0.125, 1e-9)
	assert_almost_eq(p.fraction(1.25), 0.5, 1e-9)
	assert_almost_eq(p.fraction(2.5), 1.0, 1e-9)
	var tri := TrapezoidProfile.new(0.1, 1.0, 1.0)
	assert_almost_eq(tri.duration, 2.0 * sqrt(0.1), 1e-9, "triangular profile")
	assert_eq(TrapezoidProfile.new(0.0, 1.0, 1.0).fraction(0.0), 1.0)


func test_joint_motion_is_synchronised() -> void:
	var q0 := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	var q1 := PackedFloat64Array([1.0, 0.5, 0, 0, 0, -1.0])
	var m := Ur5eJointMotion.new(q0, q1, 1.0, 2.0)
	var mid := m.sample(m.duration * 0.5, q0)
	assert_almost_eq(mid[0], 0.5, 1e-9)
	assert_almost_eq(mid[1], 0.25, 1e-9)
	assert_almost_eq(m.sample(m.duration, q0)[5], -1.0, 1e-9)


func test_linear_motion_keeps_a_straight_line() -> void:
	var tool := Basis(Vector3.RIGHT, PI)
	var q := UrKinematics.inverse_closest(Ur5eLinearMotion.flange_pose(Vector3(0.1, -0.45, 0.3), tool, 0.16),
		PackedFloat64Array([-1.57, -1.3, 1.6, -1.9, -1.57, 0]))
	assert_eq(q.size(), 6)
	var m := Ur5eLinearMotion.new(Vector3(0.1, -0.45, 0.3), Vector3(0.1, -0.45, 0.1), tool, 0.16, 0.25, 1.2)
	for i in 11:
		q = m.sample(m.duration * i / 10.0, q)
		var flange := UrKinematics.forward(q)
		var tcp := flange.origin + flange.basis.z * 0.16
		assert_almost_eq(tcp.x, 0.1, 5e-4)
		assert_almost_eq(tcp.y, -0.45, 5e-4)
