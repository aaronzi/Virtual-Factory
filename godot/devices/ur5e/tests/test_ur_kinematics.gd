extends GutTest

const HOME := [0.0, -PI / 2.0, PI / 2.0, -PI / 2.0, -PI / 2.0, 0.0]


func _poses_equal(a: Transform3D, b: Transform3D, tol := 1e-6) -> bool:
	return a.origin.distance_to(b.origin) < tol and a.basis.x.distance_to(b.basis.x) < tol \
		and a.basis.y.distance_to(b.basis.y) < tol and a.basis.z.distance_to(b.basis.z) < tol


func test_zero_pose_matches_datasheet() -> void:
	# All joints zero: arm stretched along -X: x = a2 + a3, y = -(d4 + d6), z = d1 - d5
	var t := UrKinematics.forward(PackedFloat64Array([0, 0, 0, 0, 0, 0]))
	assert_almost_eq(t.origin.x, -0.8172, 1e-4)
	assert_almost_eq(t.origin.y, -0.2329, 1e-4)
	assert_almost_eq(t.origin.z, 0.0628, 1e-4)


func test_ik_roundtrip_random_poses() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 1234
	for n in 200:
		var q := PackedFloat64Array()
		for i in 6:
			q.append(rng.randf_range(-PI, PI))
		var target := UrKinematics.forward(q)
		var sols := UrKinematics.inverse(target)
		assert_gt(sols.size(), 0, "pose %d reachable" % n)
		for sol in sols:
			# Transform3D is single precision; near the wrist singularity (sin q5 -> 0) the residual
			# grows to ~0.2 mm, which is far below the gripper tolerance.
			if not _poses_equal(UrKinematics.forward(sol), target, 5e-4):
				fail_test("IK solution does not reproduce pose %d: %s" % [n, sol])
				return
	pass_test("all IK solutions reproduce their poses")


func test_closest_solution_is_the_original_configuration() -> void:
	var q := PackedFloat64Array([0.3, -1.2, 1.5, -1.9, -1.57, 0.4])
	var sol := UrKinematics.inverse_closest(UrKinematics.forward(q), q)
	for i in 6:
		assert_almost_eq(sol[i], q[i], 1e-6)


func test_unreachable_pose_has_no_solution() -> void:
	var t := Transform3D(Basis(), Vector3(2.0, 0.0, 0.5))
	assert_eq(UrKinematics.inverse(t).size(), 0)
