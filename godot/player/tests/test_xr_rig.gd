extends GutTest
## XR rig without a headset: interface contract of PlayerRig (pointer ray from the right controller,
## teleport keeps the floor height, start fails gracefully without a runtime).


func test_xr_rig_implements_player_rig() -> void:
	var rig := XRRig.new()
	add_child_autofree(rig)
	rig.right.position = Vector3(0.2, 1.1, -0.3)
	var ray := rig.get_pointer_ray()
	assert_almost_eq(ray.origin, rig.right.global_position, Vector3.ONE * 1e-4)
	assert_almost_eq(ray.direction, Vector3.FORWARD, Vector3.ONE * 1e-4)
	assert_eq(rig.get_view_camera(), rig.head)
	rig.teleport_to(Vector3(1, 1.7, 2), Vector3(1, 1.0, 0))
	assert_eq(rig.global_position.y, 0.0, "the headset provides the eye height")


func test_start_without_runtime_returns_false() -> void:
	var rig := XRRig.new()
	add_child_autofree(rig)
	assert_false(rig.try_start())
