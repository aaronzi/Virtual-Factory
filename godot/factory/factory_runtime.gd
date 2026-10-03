extends Node3D
## Runs the factory: builds it from the layout and advances the co-simulation with the physics tick:
##   commands (UNS) -> probes sample the world -> master steps all FMI models -> UNS publishes -> views.
##
## UNS gateway (MQTT): on by default with broker.websocket from res://config/uns.json;
##   --vf-uns=<ws://host:port | mqtt://host:port> overrides the broker, --vf-uns=off disables it.

signal built(builder: FactoryBuilder)

const UNS_REGISTRY := "res://config/uns.json"

@export_file("*.json") var layout_path := "res://config/layouts/line1.layout.json"

var builder := FactoryBuilder.new()
var uns: UnsGateway
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
	_start_uns(DevTools.get_arg("vf-uns"))
	built.emit(builder)


func _physics_process(delta: float) -> void:
	if not _running:
		return
	if uns:
		uns.before_step()
	for device: DeviceNode in builder.devices.values():
		device.sample_probes(delta)
	builder.master.step(delta)
	if uns:
		uns.after_step()
	for device: DeviceNode in builder.devices.values():
		device.apply_views(delta)


func _exit_tree() -> void:
	if uns:
		uns.shutdown()
		uns = null


## Reads an FMI variable, e.g. read("PLC01.parts_ok").
func read(path: String) -> Variant:
	return builder.master.read(path)


func _start_uns(url: String) -> void:
	if url == "off":
		return
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(UNS_REGISTRY))
	if not registry is Dictionary:
		push_error("Factory: cannot parse %s" % UNS_REGISTRY)
		return
	if url == "":
		url = registry.get("broker", {}).get("websocket", "ws://localhost:9001")
	uns = UnsGateway.new(builder.master, MqttClient.new(), registry, layout_path.get_file())
	if uns.start(url) != OK:
		uns = null
