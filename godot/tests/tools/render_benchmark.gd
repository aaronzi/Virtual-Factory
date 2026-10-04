extends SceneTree
## Deterministic rendering stress fixture: 24 packed cylinders plus 3 on the belt, training UI on.
## No backend connections or retentive changes. See tools/benchmark_visuals.sh.
## Simulation is paused; this measures rendering, not the full live-service workload.


func _initialize() -> void:
	_start.call_deferred()


func _start() -> void:
	var main := load("res://factory/main.tscn").instantiate() as Node3D
	root.add_child(main)
	current_scene = main
	var factory: Node3D = main.get_node("Factory")
	factory.set_physics_process(false)
	var builder: FactoryBuilder = factory.get("builder")
	for tag in ["KLTA01", "KLTB01"]:
		var device: DeviceNode = builder.devices[tag]
		for row in 3:
			for column in 4:
				var local := Vector3(-0.1 + row * 0.1, 0.572, -0.18 + column * 0.12)
				_spawn(builder, device.to_global(local), "%s-%d-%d" % [tag, row, column])
	for i in 3:
		_spawn(builder, Vector3(-1.8 + i * 0.7, 0.853, 0), "BELT-%d" % i)
	print("[VisualBenchmark] frozen_parts=%d full_bins=2 ui=on" %
		builder.item_factory.get_active_items().size())
	# Exercise repeated quality changes while retaining animated-part materials and door hierarchy.
	for preset in [0, 2, 1, int(root.get_node("DevTools").get_arg("vf-quality", "1"))]:
		QualitySettings.apply(main, preset)


func _spawn(builder: FactoryBuilder, position: Vector3, serial: String) -> void:
	var item := builder.item_factory.spawn(Transform3D(Basis.IDENTITY, position),
		"VISUAL-" + serial, {"cap_variant": 0})
	item.freeze = true
