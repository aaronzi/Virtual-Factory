extends GutTest
## Finger wear model of the gripper (Ur5eGripperWear): linear wear per grip, symptoms, slip region, reset.


func test_wear_grows_linearly_with_the_grips_and_symptoms_follow() -> void:
	var w := Ur5eGripperWear.new(3)
	w.rate = 2e-5
	var forces := []
	for i in 40:
		assert_true(w.grip(), "no slip below 85 %% of the limit (grip %d)" % i)
		forces.append(w.force)
	assert_eq(w.cycles, 40)
	assert_almost_eq(w.wear, 8e-4, 8e-5, "40 x 20 um")
	assert_almost_eq(w.measured_wear, w.wear, 2e-5, "encoder noise of a few um")
	assert_lt(forces[-1], forces[0] - 15.0, "clamping force drops with wear")
	assert_lt(w.speed_factor(), 0.85)
	assert_eq(w.retries, 0)


func test_parts_slip_only_above_the_threshold_and_always_beyond_115_percent() -> void:
	var worn := Ur5eGripperWear.new(5, 1.0e-3)
	var held := 0
	for i in 200:
		held += 1 if worn.grip() else 0
	assert_between(held, 1, 199, "at the limit about half of the grips slip")
	var gone := Ur5eGripperWear.new(5, 1.2e-3)
	for i in 20:
		assert_false(gone.grip())
	assert_eq(gone.retries, 20)


func test_finger_change_restores_new_fingers() -> void:
	var w := Ur5eGripperWear.new(1, 9e-4)
	w.grip()
	w.replace_fingers()
	assert_eq([w.wear, w.measured_wear, w.cycles, w.retries], [0.0, 0.0, 0, 0])
	assert_almost_eq(w.force, 100.0, 1e-9)


func test_deterministic_with_the_seed() -> void:
	var a := Ur5eGripperWear.new(42, 8.8e-4)
	var b := Ur5eGripperWear.new(42, 8.8e-4)
	for i in 30:
		assert_eq(a.grip(), b.grip())
	assert_eq(a.measured_wear, b.measured_wear)
	var saved := a.save()
	var c := Ur5eGripperWear.new(0)
	c.load(saved)
	assert_eq(c.grip(), a.grip(), "state incl. RNG restored")
