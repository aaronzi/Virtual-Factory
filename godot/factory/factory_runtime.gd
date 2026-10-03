extends Node3D
## Runs the factory: builds it from the layout and advances the co-simulation with the physics tick:
##   commands (UNS) -> probes sample the world -> master steps all FMI models -> UNS publishes -> views.
##
## UNS gateway (MQTT): on by default with broker.websocket from res://config/uns.json;
##   --vf-uns=<ws://host:port | mqtt://host:port> overrides the broker, --vf-uns=off disables it.
## OPC UA path (ADR-0024): controllers in `opcua.servers` feed their communication module (plc-comm)
##   over a backplane link instead of being published by the UNS gateway. On with the UNS gateway;
##   --vf-backplane=<tcp://host:port> overrides the address (and links even with --vf-uns=off),
##   --vf-backplane=off publishes them directly over MQTT again.
## Retentive AC01 serial counter (RetentiveCounters): --vf-serial-start=<n>, --vf-retain=off.
## Training scenarios: `scenarios` (ScenarioRunner, stepped after UNS commands);
##   --vf-scenario=<id> starts one at launch.

signal built(builder: FactoryBuilder)

const UNS_REGISTRY := "res://config/uns.json"

@export_file("*.json") var layout_path := "res://config/layouts/line1.layout.json"

var builder := FactoryBuilder.new()
var uns: UnsGateway
var backplanes: Array[PlcBackplane] = []
var scenarios: ScenarioRunner
var _running := false


func _ready() -> void:
	var items := Node3D.new()
	items.name = "Items"
	add_child(items)
	var retain := RetentiveCounters.new()  # serial numbers continue across live sessions
	add_child(retain)
	builder.parameter_overrides = retain.overrides(
		DevTools.get_arg("vf-uns") != "off" and DevTools.get_arg("vf-retain") != "off")
	var err := builder.build(layout_path, self, items)
	if err != OK:
		push_error("Factory build failed: %s" % error_string(err))
		return
	_running = true
	retain.attach(builder.master)
	scenarios = ScenarioWiring.create(builder.master)
	_start_links(DevTools.get_arg("vf-uns"), DevTools.get_arg("vf-backplane"))
	built.emit(builder)


func _physics_process(delta: float) -> void:
	if not _running:
		return
	if uns:
		uns.before_step()
	for link in backplanes:
		link.before_step()
	scenarios.before_step(delta)
	for device: DeviceNode in builder.devices.values():
		device.sample_probes(delta)
	builder.master.step(delta)
	if uns:
		uns.after_step()
	for link in backplanes:
		link.after_step()
	for device: DeviceNode in builder.devices.values():
		device.apply_views(delta)


func _exit_tree() -> void:
	for link in backplanes:
		link.shutdown()
	backplanes.clear()
	if uns:
		uns.shutdown()
		uns = null


## Reads an FMI variable, e.g. read("PLC01.parts_ok").
func read(path: String) -> Variant:
	return builder.master.read(path)


func _start_links(uns_url: String, backplane_url: String) -> void:
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(UNS_REGISTRY))
	if not registry is Dictionary:
		push_error("Factory: cannot parse %s" % UNS_REGISTRY)
		return
	var opcua: Dictionary = registry.get("opcua", {})
	if backplane_url == "off" or (uns_url == "off" and backplane_url == ""):
		opcua["enabled"] = false
	var config: UnsConfig
	if uns_url != "off":
		if uns_url == "":
			uns_url = registry.get("broker", {}).get("websocket", "ws://localhost:9001")
		uns = UnsGateway.new(builder.master, MqttClient.new(), registry, layout_path.get_file())
		if uns.start(uns_url) != OK:
			uns = null
	config = uns.get_config() if uns else UnsConfig.new(registry)
	var session := uns.session_id if uns else config.make_session_id()
	for device: String in config.opcua_devices:
		var url: String = backplane_url if backplane_url != "" else opcua.servers[device].get("backplane", "")
		var link := PlcBackplane.new(builder.master, config, device, session)
		if link.start(url) == OK:
			backplanes.append(link)
