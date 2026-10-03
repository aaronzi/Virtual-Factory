extends SceneTree
## Records a slice of the running line for Blender animations (robot joints, gripper, belt travel,
## workpiece poses in Godot world coordinates) to blender/data/demo_trajectory.json.
##   godot --headless --fixed-fps 60 -s res://tests/tools/record_demo_trajectory.gd \
##       -- --from=20 --to=33 --hz=15

const OUT := "res://../blender/data/demo_trajectory.json"


func _initialize() -> void:
	var opts := {"from": 20.0, "to": 33.0, "hz": 15.0}
	for arg in OS.get_cmdline_user_args():
		var kv := arg.trim_prefix("--").split("=")
		if kv.size() == 2 and opts.has(kv[0]):
			opts[kv[0]] = kv[1].to_float()
	var main: Node = load("res://factory/main.tscn").instantiate()
	root.add_child(main)
	var f: Node = main.get_node("Factory")
	var every := roundi(60.0 / opts.hz)
	var frames := []
	var tick := 0
	while f.builder.master.time < opts.to:
		await physics_frame
		tick += 1
		if f.builder.master.time >= opts.from and tick % every == 0:
			frames.append(_sample(f))
	var data := {"hz": opts.hz, "from": opts.from, "to": opts.to, "frames": frames}
	var file := FileAccess.open(ProjectSettings.globalize_path(OUT), FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	print("recorded %d frames -> %s" % [frames.size(), ProjectSettings.globalize_path(OUT)])
	quit()


func _sample(f: Node) -> Dictionary:
	var q := []
	for i in 6:
		q.append(f.read("RB01.q%d" % (i + 1)))
	var items := []
	for item: TrackedItem in f.builder.item_factory.get_active_items():
		var t := item.global_transform
		var rot := t.basis.get_rotation_quaternion()
		items.append({"id": item.item_id, "variant": item.properties.get("cap_variant", 0),
			"p": [t.origin.x, t.origin.y, t.origin.z], "q": [rot.x, rot.y, rot.z, rot.w]})
	return {"t": f.builder.master.time, "q": q, "gripper": f.read("RB01.gripper_width"),
		"belt": f.read("CV01.belt_position"), "items": items}
