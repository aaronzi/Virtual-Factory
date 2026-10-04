class_name BakedLighting
extends LightmapGI
## Baked lighting for static geometry (ADR-0031). The hall floor, device bodies, stands and props use a
## LightmapGI bake (indirect light, sky occlusion and a shadowmask of the high-bay key light). They no
## longer render into the real-time shadow map, which then holds only moving casters (robot, door,
## workpieces); the key light's shadowmask "overlay" combines both. Moving parts (MovingParts) and small
## parts stay dynamic and are lit by the baked light probes.
##
## The bake is made from the same layout by tools/bake_lighting.sh. User paths are relative to the scene
## root, so the node is added directly below it under NODE_NAME. If a user's mesh or placement no longer
## matches the manifest, the bake is stale: nothing is changed and real-time shadows stay in use.

enum Role { BAKED, DYNAMIC, SHELL, CARD }

const NODE_NAME := &"BakedLighting"
const ROOTS: Array[String] = ["Hall", "Factory"]  ## subtrees that take part in the bake
## Hall parts in the bake; the rest of the shell neither receives nor occludes (key light as in ADR-0010).
const HALL_BAKED: Array[String] = ["Floor", "FloorZone"]
const MIN_EXTENT := 0.2  ## smaller parts (lamps, LEDs, light barriers) stay dynamic
const MANIFEST := "manifest.json"
const LIGHTMAP := "lighting.lmbake"
const TOLERANCE := 0.002  ## m / transform components
const UV2_TOLERANCE := 1e-4  ## UV2 moments

var _root: Node
var _users := {}  ## baked user paths (String) -> true


## Applies the bake in `dir` to `root`'s factory. Returns false (and changes nothing) if there is no bake
## or it is stale.
static func apply(root: Node3D, dir: String) -> bool:
	var manifest := load_manifest(dir)
	if manifest.is_empty() or not ResourceLoader.exists(dir.path_join(LIGHTMAP)):
		return false
	var problems := validate(root, manifest)
	if not problems.is_empty():
		push_warning("Baked lighting in %s is stale (%d differences, first: %s); using real-time shadows. "
			% [dir, problems.size(), problems[0]] + "Rebake with tools/bake_lighting.sh.")
		return false
	var data := load(dir.path_join(LIGHTMAP)) as LightmapGIData
	var gi := BakedLighting.new()
	gi.name = NODE_NAME
	gi._root = root
	for i in data.get_user_count():
		var path := String(data.get_user_path(i)).trim_prefix("../")  # stored relative to the LightmapGI
		if manifest.users.has(path):
			gi._users[path] = true
			_make_baked(root, root.get_node(path), manifest.users[path])
	configure(gi, manifest.get("settings", {}))
	root.add_child(gi)
	for root_name in ROOTS:
		gi._set_dynamic(root.get_node_or_null(root_name))
	gi.light_data = data
	return true


## Classification shared by the bake and the runtime (see the class description).
static func role(root: Node, mi: MeshInstance3D) -> Role:
	var path := String(root.get_path_to(mi))
	if mi.name == &"ContactShadow":
		return Role.CARD
	if path.begins_with("Hall/"):
		return Role.BAKED if String(mi.name) in HALL_BAKED else Role.SHELL
	if not mi.is_visible_in_tree() or mi.mesh == null or path.contains("@") or MovingParts.is_moving(mi):
		return Role.DYNAMIC
	if String(mi.name).begins_with("Detail") or _transparent(mi):
		return Role.DYNAMIC
	var size := mi.get_aabb().size * mi.global_basis.get_scale().abs()
	return Role.BAKED if maxf(size.x, maxf(size.y, size.z)) >= MIN_EXTENT else Role.DYNAMIC


## Baked meshes below the ROOTS of `root`, keyed by their path relative to `root`.
static func classify(root: Node) -> Dictionary:
	var out := {}
	for root_name in ROOTS:
		var sub := root.get_node_or_null(root_name)
		if sub == null:
			continue
		for mi: MeshInstance3D in sub.find_children("*", "MeshInstance3D", true, false):
			if role(root, mi) == Role.BAKED:
				out[String(root.get_path_to(mi))] = mi
	return out


## Placement and geometry of a baked mesh; any change makes the bake stale. Compared with tolerances
## (float results differ in the last bits between platforms and compilers): UV2 as moments (means of u, v,
## u², v², uv) - a different lightmap unwrap changes them far beyond UV2_TOLERANCE.
static func fingerprint(root: Node3D, mi: MeshInstance3D) -> Dictionary:
	if mi.has_meta(&"baked_source"):
		return mi.get_meta(&"baked_source")  # procedural mesh already swapped for its UV2 copy
	var xform := root.global_transform.affine_inverse() * mi.global_transform
	var vertices := 0
	var uv2 := [0.0, 0.0, 0.0, 0.0, 0.0]
	var uv2_count := 0
	for s in mi.mesh.get_surface_count():
		var arrays := mi.mesh.surface_get_arrays(s)
		vertices += (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		if arrays[Mesh.ARRAY_TEX_UV2] == null:
			continue
		for uv: Vector2 in arrays[Mesh.ARRAY_TEX_UV2]:
			uv2[0] += uv.x
			uv2[1] += uv.y
			uv2[2] += uv.x * uv.x
			uv2[3] += uv.y * uv.y
			uv2[4] += uv.x * uv.y
		uv2_count += (arrays[Mesh.ARRAY_TEX_UV2] as PackedVector2Array).size()
	var box := mi.mesh.get_aabb()
	return {"vertices": vertices, "uv2": uv2.map(func(m: float) -> float: return m / maxi(uv2_count, 1)),
		"xform": _floats(xform), "aabb": [
		box.position.x, box.position.y, box.position.z, box.size.x, box.size.y, box.size.z]}


## Differences between the scene and the manifest (empty = the bake matches). Meshes built at runtime
## (entry "mesh", e.g. merged conveyor parts) are replaced by their saved unwrapped copy, so only their
## geometry and placement count, not the UV2 of the runtime merge.
static func validate(root: Node3D, manifest: Dictionary) -> PackedStringArray:
	var problems := PackedStringArray()
	var current := classify(root)
	var users: Dictionary = manifest.get("users", {})
	for path: String in users:
		if not current.has(path):
			problems.append("%s: missing or no longer static" % path)
			continue
		var now := fingerprint(root, current[path])
		var then: Dictionary = users[path]
		if int(now.vertices) != int(then.get("vertices", -1)):
			problems.append("%s: vertices changed" % path)
		var checks := {"xform": TOLERANCE, "aabb": TOLERANCE}
		if not then.has("mesh"):
			checks["uv2"] = UV2_TOLERANCE
		for key: String in checks:
			if not _close(now[key], then.get(key, []), checks[key]):
				problems.append("%s: %s changed" % [path, key])
	for path: String in current:
		if not users.has(path):
			problems.append("%s: new static mesh not in the bake" % path)
	return problems


static func load_manifest(dir: String) -> Dictionary:
	var path := dir.path_join(MANIFEST)
	if not FileAccess.file_exists(path):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary and data.has("users") else {}


## LightmapGI settings shared by the bake scene and the runtime node.
static func configure(gi: LightmapGI, settings: Dictionary) -> void:
	gi.shadowmask_mode = LightmapGIData.SHADOWMASK_MODE_OVERLAY
	gi.directional = false
	gi.interior = false
	gi.quality = int(settings.get("quality", LightmapGI.BAKE_QUALITY_HIGH)) as LightmapGI.BakeQuality
	gi.bounces = int(settings.get("bounces", 3))
	gi.texel_scale = float(settings.get("texel_scale", 1.0))
	gi.max_texture_size = int(settings.get("max_texture_size", 4096))
	gi.supersampling = bool(settings.get("supersampling", false))
	gi.environment_mode = LightmapGI.ENVIRONMENT_MODE_CUSTOM_COLOR
	var c: Array = settings.get("environment_color", [0.84, 0.87, 0.92])
	gi.environment_custom_color = Color(c[0], c[1], c[2])
	gi.environment_custom_energy = float(settings.get("environment_energy", 0.24))
	gi.generate_probes_subdiv = LightmapGI.GENERATE_PROBES_SUBDIV_8


static func _make_baked(root: Node3D, mi: MeshInstance3D, entry: Dictionary) -> void:
	if entry.has("mesh"):  # procedural mesh (e.g. merged conveyor parts): same geometry with lightmap UV2
		mi.set_meta(&"baked_source", fingerprint(root, mi))
		var old := mi.mesh
		mi.mesh = load(entry.mesh)
		for s in old.get_surface_count():
			if mi.get_surface_override_material(s) == null:
				mi.set_surface_override_material(s, old.surface_get_material(s))
	mi.gi_mode = GeometryInstance3D.GI_MODE_STATIC
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # in the shadowmask instead


## Glass, labels and screens (decal surfaces on an opaque body are baked with it).
static func _transparent(mi: MeshInstance3D) -> bool:
	for s in mi.mesh.get_surface_count():
		var mat := mi.get_active_material(s) as BaseMaterial3D
		if mat == null or mat.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED:
			return false
	return true


static func _floats(xform: Transform3D) -> Array:
	var b := xform.basis
	return [b.x.x, b.x.y, b.x.z, b.y.x, b.y.y, b.y.z, b.z.x, b.z.y, b.z.z,
		xform.origin.x, xform.origin.y, xform.origin.z]


static func _close(a: Array, b: Array, tolerance: float) -> bool:
	if a.size() != b.size():
		return false
	for i in a.size():
		if absf(float(a[i]) - float(b[i])) > tolerance:
			return false
	return true


func _enter_tree() -> void:
	if not get_tree().node_added.is_connected(_on_node_added):
		get_tree().node_added.connect(_on_node_added)


func _exit_tree() -> void:
	if get_tree().node_added.is_connected(_on_node_added):
		get_tree().node_added.disconnect(_on_node_added)


## Everything below `node` that is not baked: light probes (moving parts) or the plain environment (hall
## shell); contact-shadow cards are replaced by the baked occlusion.
func _set_dynamic(node: Node) -> void:
	if node == null:
		return
	for mi: MeshInstance3D in node.find_children("*", "MeshInstance3D", true, false):
		_on_node_added(mi)


func _on_node_added(node: Node) -> void:
	var mi := node as MeshInstance3D
	if mi == null or _root == null or not _root.is_ancestor_of(mi) \
			or _users.has(String(_root.get_path_to(mi))):
		return
	match role(_root, mi):
		Role.CARD:
			mi.visible = false
		Role.SHELL:
			mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		_:
			mi.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC  # also late additions such as workpieces
