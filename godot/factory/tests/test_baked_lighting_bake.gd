extends GutTest
## The committed lighting bake (ADR-0031) must match the runtime layout: same static meshes, placements and
## lightmap UV2. Fails after layout or asset changes until tools/bake_lighting.sh is run again.

const LAYOUT := "res://config/layouts/line1.layout.json"
const BAKE := "res://world/lighting/baked/line1"

var _root: Node3D
var _builder: FactoryBuilder


func before_each() -> void:
	_root = Node3D.new()
	add_child_autofree(_root)
	var hall := Hall.new()
	hall.name = "Hall"
	_root.add_child(hall)
	var factory := Node3D.new()
	factory.name = "Factory"
	_root.add_child(factory)
	var items := Node3D.new()
	factory.add_child(items)
	_builder = FactoryBuilder.new()
	assert_eq(_builder.build(LAYOUT, factory, items), OK)


func test_bake_is_not_stale() -> void:
	var manifest := BakedLighting.load_manifest(BAKE)
	assert_false(manifest.is_empty(), "bake manifest present")
	assert_eq(BakedLighting.validate(_root, manifest), PackedStringArray(),
		"bake matches layout and assets (otherwise run tools/bake_lighting.sh)")
	var data := load(BAKE.path_join(BakedLighting.LIGHTMAP)) as LightmapGIData
	var baked := []
	for i in data.get_user_count():
		baked.append(String(data.get_user_path(i)).trim_prefix("../"))
	baked.sort()
	var expected: Array = manifest.users.keys()
	expected.sort()
	assert_eq(baked, expected, "every static mesh received a lightmap")
	assert_eq(data.shadowmask_textures.size(), 1, "key-light shadowmask baked")


func test_static_and_dynamic_shadow_flags() -> void:
	var problems := BakedLighting.validate(_root, BakedLighting.load_manifest(BAKE))
	if not BakedLighting.apply(_root, BAKE):
		fail_test("bake not applied (missing or stale: %s) - run tools/bake_lighting.sh" % [problems])
		return
	var gi := _root.get_node_or_null(String(BakedLighting.NODE_NAME)) as LightmapGI
	if gi == null:
		fail_test("BakedLighting node missing after apply")
		return
	assert_eq(gi.shadowmask_mode, LightmapGIData.SHADOWMASK_MODE_OVERLAY)
	var floor_zone := _root.get_node("Hall/hall/FloorZone") as GeometryInstance3D
	assert_eq(floor_zone.gi_mode, GeometryInstance3D.GI_MODE_STATIC)
	var cell := _root.get_node("Factory/AC01/View/assembly_cell/Cell") as GeometryInstance3D
	assert_eq(cell.gi_mode, GeometryInstance3D.GI_MODE_STATIC)
	assert_eq(cell.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "static: shadowmask only")
	var link := _root.find_child("Link2", true, false) as GeometryInstance3D
	assert_eq(link.gi_mode, GeometryInstance3D.GI_MODE_DYNAMIC, "robot lit by light probes")
	assert_eq(link.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON, "robot casts real-time shadows")
	var door := _root.find_child("Door", true, false) as GeometryInstance3D
	assert_eq(door.gi_mode, GeometryInstance3D.GI_MODE_DYNAMIC)
	assert_eq(door.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON, "hinged door casts real-time")
	var walls := _root.get_node("Hall/hall/Walls") as GeometryInstance3D
	assert_eq(walls.gi_mode, GeometryInstance3D.GI_MODE_DISABLED, "hall shell is not part of the bake")
	for card: Node3D in _root.find_children("ContactShadow", "MeshInstance3D", true, false):
		assert_false(card.visible, "contact cards replaced by baked occlusion")
	var conveyor := _root.get_node("Factory/CV01/View/StaticParts") as MeshInstance3D
	assert_true(conveyor.mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_TEX_UV2 != 0, "unwrapped copy")
	assert_not_null(conveyor.get_active_material(0), "keeps its materials")
	var late := MeshInstance3D.new()
	late.mesh = BoxMesh.new()
	_root.get_node("Factory").add_child(late)
	assert_eq(late.gi_mode, GeometryInstance3D.GI_MODE_DYNAMIC, "workpieces added later use probes")
