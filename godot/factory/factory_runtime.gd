extends Node3D
## Runs the factory: builds it from the layout and advances the co-simulation with the physics tick:
##   probes sample the world -> master steps all FMI models -> views update the world.

signal built(builder: FactoryBuilder)

@export_file("*.json") var layout_path := "res://config/layouts/line1.layout.json"

var builder := FactoryBuilder.new()
var _running := false


func _ready() -> void:
	var items := Node3D.new()
	items.name = "Items"
	add_child(items)
	var err := builder.build(layout_path, self, items)
	if err != OK:
		push_error("Factory build failed: %s" % error_string(err))
		return
	_running = true
	built.emit(builder)


func _physics_process(delta: float) -> void:
	if not _running:
		return
	for device: DeviceNode in builder.devices.values():
		device.sample_probes(delta)
	builder.master.step(delta)
	for device: DeviceNode in builder.devices.values():
		device.apply_views(delta)


## Reads an FMI variable, e.g. read("PLC01.parts_ok").
func read(path: String) -> Variant:
	return builder.master.read(path)
