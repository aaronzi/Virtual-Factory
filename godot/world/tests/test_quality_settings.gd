extends GutTest
## Real imported assets catch lost vertex colours, material swaps and detail nodes that fail to restore.


func test_quality_round_trip_preserves_assets() -> void:
	var root := Node3D.new()
	add_child_autofree(root)
	var fence := preload("res://world/props/safety_fence.glb").instantiate()
	root.add_child(fence)
	var hall := preload("res://world/hall/hall.glb").instantiate()
	root.add_child(hall)
	var wire := fence.find_child("DetailDoorWire", true, false) as MeshInstance3D
	assert_not_null(wire)
	assert_eq(wire.get_parent().name, &"Door", "wire follows the hinged door")
	var floor_mesh := hall.find_child("FloorZone", true, false) as MeshInstance3D  # epoxy production zone
	var epoxy: BaseMaterial3D
	for surface in floor_mesh.mesh.get_surface_count():
		var mat := floor_mesh.mesh.surface_get_material(surface)
		if mat.resource_name == "VF_epoxy":
			epoxy = mat
	assert_not_null(epoxy)
	var light := DirectionalLight3D.new()
	light.shadow_enabled = true
	root.add_child(light)
	QualitySettings.apply(root, QualitySettings.Preset.HIGH)
	var texture := epoxy.albedo_texture
	assert_not_null(texture)
	assert_true(epoxy.normal_enabled)
	QualitySettings.apply(root, QualitySettings.Preset.LOW)
	assert_false(wire.visible)
	assert_false(light.shadow_enabled)
	assert_null(epoxy.albedo_texture)
	assert_false(epoxy.normal_enabled)
	QualitySettings.apply(root, QualitySettings.Preset.HIGH)
	assert_true(wire.visible)
	assert_true(light.shadow_enabled)
	assert_same(epoxy.albedo_texture, texture, "texture restored without rebuilding assets")
	QualitySettings.apply(root, QualitySettings.Preset.MEDIUM)
	assert_true(wire.visible)
	assert_false(epoxy.normal_enabled)
	assert_not_null(epoxy.albedo_texture)


func test_batched_material_and_robot_contract() -> void:
	var robot := preload("res://devices/ur5e/view/ur5e.glb").instantiate()
	add_child_autofree(robot)
	for index in range(1, 7):
		assert_not_null(robot.find_child("J%d" % index, true, false))
	var link := robot.find_child("Link2", true, false) as MeshInstance3D
	assert_eq(link.mesh.get_surface_count(), 1, "colour batching keeps the robot cheap")
	assert_true(link.mesh.surface_get_material(0) is ShaderMaterial)
	assert_gt(link.mesh.surface_get_arrays(0)[Mesh.ARRAY_COLOR].size(), 0)
