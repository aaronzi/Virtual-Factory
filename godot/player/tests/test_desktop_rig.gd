extends GutTest

const RigScene := preload("res://player/desktop_rig.tscn")


func test_camera_stays_inside_bounds() -> void:
	var rig: DesktopRig = RigScene.instantiate()
	add_child_autofree(rig)
	rig.bounds = AABB(Vector3(-17.65, 0.3, -11.65), Vector3(35.3, 7.3, 23.3))
	rig.teleport_to(Vector3(40, 20, -30), Vector3.ZERO)
	assert_almost_eq(rig.global_position, Vector3(17.65, 7.6, -11.65), Vector3.ONE * 1e-4,
		"clamped to walls and below the ceiling")
	rig.teleport_to(Vector3(0, -5, 0), Vector3(0, 1, -1))
	assert_almost_eq(rig.global_position.y, 0.3, 1e-4, "never below eye-safe floor height")
