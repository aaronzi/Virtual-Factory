extends SceneTree
## Step 1 of tools/bake_lighting.sh (ADR-0031): builds the main scene headless, exactly as at runtime, and
## mirrors every baked mesh (BakedLighting.classify) with its path, transform and materials into a bake
## scene next to the lights and a configured LightmapGI. Procedural meshes without lightmap UV2 (merged
## conveyor parts) are unwrapped and saved under meshes/. The manifest records each mesh's fingerprint,
## so the runtime and the tests detect a stale bake. Step 2 bakes the scene in the editor.
##
## Args (after --): --vf-bake-main=<main scene> --vf-bake-dir=<output dir> [--vf-bake-settings=<json>]

const SCENE := "bake_scene.scn"  ## not versioned (embeds mesh copies); regenerated for every bake
const LIGHTS: Array[String] = ["HighBayLight", "FillLight", "WorldEnvironment"]


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var tools := root.get_node("DevTools")
	var dir: String = tools.get_arg("vf-bake-dir")
	var settings: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(tools.get_arg("vf-bake-settings", dir.path_join("settings.json"))))
	var main := (load(tools.get_arg("vf-bake-main")) as PackedScene).instantiate() as Node3D
	root.add_child(main)
	for i in 3:
		await process_frame
	DirAccess.make_dir_recursive_absolute(dir.path_join("meshes"))
	var scene := Node3D.new()
	scene.name = main.name
	for light_name in LIGHTS:
		_own(scene, _add(scene, main.get_node(light_name).duplicate()))
	var key := scene.get_node_or_null("HighBayLight") as DirectionalLight3D
	if key:  # soft penumbra of the baked key-light shadows
		key.light_angular_distance = float(settings.get("key_light_angular_distance", 0.0))
	var users := {}
	var meshes := BakedLighting.classify(main)
	for path: String in meshes:
		users[path] = _mirror(main, scene, path, meshes[path], dir, settings)
	var gi := LightmapGI.new()
	gi.name = BakedLighting.NODE_NAME
	BakedLighting.configure(gi, settings)
	_own(scene, _add(scene, gi))
	var packed := PackedScene.new()
	var err := packed.pack(scene)
	if err == OK:
		err = ResourceSaver.save(packed, dir.path_join(SCENE))
	_write_manifest(dir, settings, users)
	print("[BakeScene] %d static meshes -> %s (%s)" % [users.size(), dir.path_join(SCENE), error_string(err)])
	main.free()
	scene.free()
	quit(0 if err == OK else 1)


## Copies `mi` into `scene` at the same path below the root; returns its manifest entry.
func _mirror(main: Node3D, scene: Node3D, path: String, mi: MeshInstance3D, dir: String,
		settings: Dictionary) -> Dictionary:
	var entry := BakedLighting.fingerprint(main, mi)
	var parent: Node = scene
	var source: Node = main
	var names := path.split("/")
	for i in names.size() - 1:
		source = source.get_node(names[i])
		var next := parent.get_node_or_null(names[i])
		if next == null:
			next = Node3D.new()
			next.name = names[i]
			next.transform = (source as Node3D).transform
			_own(scene, _add(parent, next))
		parent = next
	var copy := MeshInstance3D.new()
	copy.name = mi.name
	copy.transform = mi.transform
	copy.mesh = mi.mesh
	if mi.mesh.resource_path.is_empty() or not _has_uv2(mi.mesh):  # built at runtime: unique unwrap
		entry["mesh"] = _unwrap(mi, dir.path_join("meshes/%s.res" % path.replace("/", "_")), settings)
		copy.mesh = load(entry.mesh)
	copy.material_override = mi.material_override
	for s in mi.mesh.get_surface_count():
		copy.set_surface_override_material(s, mi.get_active_material(s))
	copy.gi_mode = GeometryInstance3D.GI_MODE_STATIC
	copy.gi_lightmap_texel_scale = float(settings.get("texel_scale_overrides", {}).get(path, 1.0))
	copy.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	_own(scene, _add(parent, copy))
	return entry


## Lightmap UV2 for a procedural mesh, saved without materials (the runtime keeps its own).
func _unwrap(mi: MeshInstance3D, path: String, settings: Dictionary) -> String:
	var mesh := (mi.mesh as ArrayMesh).duplicate(true) as ArrayMesh
	for s in mesh.get_surface_count():
		mesh.surface_set_material(s, null)
	var err := mesh.lightmap_unwrap(mi.global_transform, float(settings.get("unwrap_texel_size", 0.1)))
	if err != OK or mesh.get_surface_count() != mi.mesh.get_surface_count():
		push_error("BakeScene: cannot unwrap %s (%s)" % [mi.get_path(), error_string(err)])
	ResourceSaver.save(mesh, path)
	return path


func _write_manifest(dir: String, settings: Dictionary, users: Dictionary) -> void:
	var manifest := {
		"format": 1,
		"godot": Engine.get_version_info().string,
		"settings": settings,
		"users": users,
	}
	var file := FileAccess.open(dir.path_join(BakedLighting.MANIFEST), FileAccess.WRITE)
	file.store_string(JSON.stringify(manifest, "  ", true) + "\n")


static func _has_uv2(mesh: Mesh) -> bool:
	for s in mesh.get_surface_count():
		if not mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_TEX_UV2:
			return false
	return mesh.get_surface_count() > 0


static func _add(parent: Node, child: Node) -> Node:
	parent.add_child(child)
	return child


static func _own(scene: Node, node: Node) -> void:
	node.owner = scene
	for child in node.get_children():
		_own(scene, child)
