extends GutTest
## Static/dynamic classification and stale-bake detection of BakedLighting (ADR-0031) on a synthetic scene.

var _root: Node3D


func before_each() -> void:
	_root = Node3D.new()
	add_child_autofree(_root)
	var hall := _node(_root, "Hall")
	_mesh(hall, "Floor", Vector3(10, 0.1, 10))
	_mesh(hall, "Walls", Vector3(10, 4, 0.2))
	var device := _node(_node(_root, "Factory"), "DEV01")
	device.position = Vector3(1, 0, 2)
	_mesh(device, "Body", Vector3(0.5, 1, 0.5))
	_mesh(device, "Lamp", Vector3(0.05, 0.05, 0.05))
	_mesh(device, "ContactShadow", Vector3(1, 0.001, 1))
	_mesh(device, "DetailWire", Vector3(1, 1, 0.01))
	var arm := _node(device, "J1")
	MovingParts.mark(arm)
	_mesh(arm, "Link", Vector3(0.1, 0.6, 0.1))
	var glass := _mesh(device, "Glass", Vector3(1, 1, 0.01))
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.material_override = mat


func test_roles() -> void:
	var expected := {
		"Hall/Floor": BakedLighting.Role.BAKED, "Hall/Walls": BakedLighting.Role.SHELL,
		"Factory/DEV01/Body": BakedLighting.Role.BAKED, "Factory/DEV01/Lamp": BakedLighting.Role.DYNAMIC,
		"Factory/DEV01/ContactShadow": BakedLighting.Role.CARD,
		"Factory/DEV01/DetailWire": BakedLighting.Role.DYNAMIC,
		"Factory/DEV01/J1/Link": BakedLighting.Role.DYNAMIC, "Factory/DEV01/Glass": BakedLighting.Role.DYNAMIC,
	}
	for path: String in expected:
		assert_eq(BakedLighting.role(_root, _root.get_node(path)), expected[path], path)
	assert_eq(BakedLighting.classify(_root).keys(), ["Hall/Floor", "Factory/DEV01/Body"])


func test_validate_detects_layout_and_geometry_changes() -> void:
	var manifest := _manifest()
	assert_eq(BakedLighting.validate(_root, manifest), PackedStringArray())
	(_root.get_node("Factory/DEV01") as Node3D).position.x += 0.1
	assert_eq(BakedLighting.validate(_root, manifest).size(), 1, "moved device")
	(_root.get_node("Factory/DEV01") as Node3D).position.x -= 0.1
	(_root.get_node("Factory/DEV01/Body") as MeshInstance3D).mesh = SphereMesh.new()
	assert_gt(BakedLighting.validate(_root, manifest).size(), 0, "different geometry")
	_mesh(_root.get_node("Factory"), "NewProp", Vector3(1, 1, 1))
	assert_true(Array(BakedLighting.validate(_root, manifest)).any(
		func(p: String) -> bool: return p.contains("NewProp")), "new static prop")


func test_validate_tolerates_platform_float_noise() -> void:
	var box := (_root.get_node("Factory/DEV01/Body") as MeshInstance3D).mesh as BoxMesh
	box.add_uv2 = true
	var manifest := _manifest()
	var entry: Dictionary = manifest.users["Factory/DEV01/Body"]
	assert_gt(float(entry.uv2[0]), 0.0, "UV2 moments recorded")
	entry.uv2[0] = float(entry.uv2[0]) + 2e-5
	entry.xform[9] = float(entry.xform[9]) + 1e-5
	assert_eq(BakedLighting.validate(_root, manifest), PackedStringArray(), "last-bit differences")
	entry.uv2[0] = float(entry.uv2[0]) + 0.01
	assert_eq(BakedLighting.validate(_root, manifest).size(), 1, "different lightmap unwrap")
	entry["mesh"] = "res://saved_unwrap.res"
	assert_eq(BakedLighting.validate(_root, manifest), PackedStringArray(),
		"runtime-built meshes use their saved unwrap: runtime UV2 irrelevant")


func test_apply_without_bake_changes_nothing() -> void:
	assert_false(BakedLighting.apply(_root, "res://world/tests/no_such_bake"))
	var body := _root.get_node("Factory/DEV01/Body") as MeshInstance3D
	assert_eq(body.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON)
	assert_true((_root.get_node("Factory/DEV01/ContactShadow") as Node3D).visible)
	assert_null(_root.get_node_or_null(String(BakedLighting.NODE_NAME)))


func test_configure_uses_shadowmask_overlay() -> void:
	var gi := LightmapGI.new()
	BakedLighting.configure(gi, {"texel_scale": 2.0, "environment_energy": 0.3})
	assert_eq(gi.shadowmask_mode, LightmapGIData.SHADOWMASK_MODE_OVERLAY)
	assert_eq(gi.texel_scale, 2.0)
	assert_almost_eq(gi.environment_custom_energy, 0.3, 1e-6)
	gi.free()


func _manifest() -> Dictionary:
	var users := {}
	var meshes := BakedLighting.classify(_root)
	for path: String in meshes:
		users[path] = JSON.parse_string(JSON.stringify(BakedLighting.fingerprint(_root, meshes[path])))
	return {"users": users}


static func _node(parent: Node, node_name: String) -> Node3D:
	var node := Node3D.new()
	node.name = node_name
	parent.add_child(node)
	return node


static func _mesh(parent: Node, node_name: String, size: Vector3) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = node_name
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	parent.add_child(mi)
	return mi


func test_low_preset_keeps_shadowmask_without_casters() -> void:
	var light := DirectionalLight3D.new()
	light.shadow_enabled = true
	_root.add_child(light)
	_root.add_child(LightmapGI.new())
	QualitySettings.apply(_root, QualitySettings.Preset.LOW)
	assert_true(light.shadow_enabled, "the shadowmask needs a shadowed light")
	assert_eq(light.shadow_caster_mask, 0, "no real-time casters on Low")
	QualitySettings.apply(_root, QualitySettings.Preset.HIGH)
	assert_eq(light.shadow_caster_mask, 0xFFFFFFFF)
