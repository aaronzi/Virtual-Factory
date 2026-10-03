class_name TrainingUi
extends Node
## Composition of the in-world training UI (part of the composition root): pointer routing, asset picking,
## AAS inspector with BaSyx events, and the backend clients. Endpoints: res://config/backend.json,
## `--vf-aas-url=`, `--vf-bpmn-url=`, `--vf-resolver-url=`, `--vf-alarms-url=`,
## `--vf-aas-events=<broker url|off>` (default:
## broker of uns.json), `--vf-inspect=<asset tag | serial | asset id>` opens the inspector at start;
## `--vf-estop=1` presses the E-stop. Secure compose profile (ADR-0027): `--vf-secure` logs the training
## user in (token for AAS, DPP, alarms) and uses the broker / Operaton accounts (SecureProfile).

const BACKEND := "res://config/backend.json"
const UNS := "res://config/uns.json"

var factory: Node
var rig: PlayerRig
var config := {}
var aas: AasClient
var feed: AasEventFeed
var router: PointerRouter
var inspector: InspectorController
var commands: LocalCommands
var hmi: HmiController
var tasks: TaskController
var menu: MenuController
var dataflow: DataFlowController
var fence_door: FenceDoorController
var safety: SafetyCircuit
var hover: HoverHighlight
var secure: SecureProfile
var session: OidcSession


func setup(p_factory: Node, p_rig: PlayerRig) -> void:
	factory = p_factory
	rig = p_rig
	config = _load_json(BACKEND)
	_start_login()
	aas = AasClient.new()
	aas.base_url = DevTools.get_arg("vf-aas-url", config.get("aas_url", "http://localhost:8091"))
	aas.id_base = config.get("id_base", aas.id_base)
	aas.registries = config.get("aas_registries", [])
	add_child(aas)
	_start_feed()
	router = PointerRouter.new()
	add_child(router)
	router.rig = rig
	router.world_pressed.connect(_on_world_pressed)
	AssetPicker.add_volumes(factory.builder)
	hover = HoverHighlight.new()
	add_child(hover)
	hover.setup(rig, router)
	inspector = InspectorController.new()
	add_child(inspector)
	inspector.setup(aas, feed, rig)
	inspector.actions_provider = _actions_for
	inspector.action_handler = _on_action
	commands = LocalCommands.new(factory.builder.master)
	process_physics_priority = -10  # local commands are applied before the factory steps the co-simulation
	_setup_hmi()
	_setup_tasks()
	_setup_fence_door()
	dataflow = DataFlowController.new()
	add_child(dataflow)
	dataflow.setup(factory.builder, factory.get("uns"), feed, factory.get("backplanes"))
	menu = MenuController.new()
	add_child(menu)
	menu.setup(self)
	var inspect := DevTools.get_arg("vf-inspect")
	if inspect != "":
		get_tree().create_timer(1.0).timeout.connect(func() -> void:
			inspector.open_asset(asset_id_for(inspect)))
	if DevTools.get_arg("vf-estop") != "":
		get_tree().create_timer(1.0).timeout.connect(safety.toggle_estop)


## Secure profile: login of the training user (token for AAS, DPP, alarms; ADR-0027), no-op otherwise.
func _start_login() -> void:
	secure = SecureProfile.new(config)
	session = secure.start_login(self)


func _process(_delta: float) -> void:
	if feed:
		feed.poll()


func _physics_process(_delta: float) -> void:
	commands.apply()


func _exit_tree() -> void:
	if feed:
		feed.stop()


func _on_world_pressed(_hit: Dictionary) -> void:
	var picked := AssetPicker.pick(rig.get_world_3d(), rig.get_pointer_ray())
	if not picked.is_empty():
		var item := picked.node as TrackedItem
		var id := item.get_asset_id() if item and item.get_asset_id() != "" else asset_id_for(picked.tag)
		inspector.open_asset(id, picked.get("point", Vector3.INF))


func set_dataflow(on: bool) -> void:
	dataflow.set_visible(on)


func _setup_hmi() -> void:
	for prop: Node3D in factory.builder.props:
		if prop.scene_file_path.ends_with("hmi_stand.glb"):
			hmi = HmiController.new()
			add_child(hmi)
			hmi.setup(factory.builder.master, commands, prop)
			var client := AlarmsClient.new()
			client.base_url = DevTools.get_arg("vf-alarms-url", config.get("alarms_url", client.base_url))
			hmi.add_child(client)
			hmi.alarms = client
			return


func _setup_fence_door() -> void:
	safety = SafetyCircuit.new()
	add_child(safety)
	safety.setup(factory.builder.master, commands)
	for prop: Node3D in factory.builder.props:
		if prop.scene_file_path.ends_with("hmi_stand.glb"):
			safety.add_estop(prop)
	for prop: Node3D in factory.builder.props:
		if prop.scene_file_path.ends_with("safety_fence.glb"):
			fence_door = FenceDoorController.new()
			fence_door.safety = safety
			add_child(fence_door)
			if not fence_door.setup(factory.builder.master, commands, prop):
				push_warning("TrainingUi: safety fence has no Door object")
			return


func _setup_tasks() -> void:
	var bpmn := BpmnTasks.new()
	bpmn.base_url = DevTools.get_arg("vf-bpmn-url", config.get("bpmn_url", bpmn.base_url))
	bpmn.authorization = secure.bpmn_authorization()
	add_child(bpmn)
	tasks = TaskController.new()
	tasks.poll_s = config.get("task_poll_s", 2.0)
	add_child(tasks)
	var pos: Array = config.get("terminal_position", [2.25, 0.0, -1.05])
	tasks.setup(bpmn, factory, Vector3(pos[0], pos[1], pos[2]), config.get("terminal_yaw_deg", -10.0))
	tasks.tasks_changed.connect(inspector.refresh_actions)


## Global asset id of a picked asset: workpieces (tag WP_<serial> or a serial) by their GS1 Digital Link,
## devices and props by their asset id (`<id_base>/asset/<tag>`); full ids are passed through.
func asset_id_for(tag: String) -> String:
	if tag.contains("://"):
		return tag
	if tag.begins_with("WP_") or tag.begins_with("PC3280-"):
		var serial := tag.trim_prefix("WP_").replace("_", "-")
		return DigitalLink.item(config.get("product_gtin", "04099999032808"), serial)
	return aas.asset_id(tag)


## Context actions of the inspector: KLT stations offer the exchange (BPMN task or direct command),
## workpieces "scan" their QR code: the Digital Link opens on the GS1 resolver (passport page, browser).
func _actions_for(tag: String) -> Array:
	if tag.begins_with("WP_"):
		return [{"id": "scan_qr", "label": tr("INSPECTOR_SCAN_QR")}]
	var container: int = {"KLTA01": 1, "KLTB01": 2}.get(tag, 0)
	if container == 0:
		return []
	if tasks and tasks.exchange_tasks.has(container):
		return [{"id": "complete_exchange", "label": tr("KLT_EXCHANGE_TASK")}]
	return [{"id": "exchange", "label": tr("KLT_EXCHANGE_NOW")}]


func _on_action(tag: String, action_id: String) -> void:
	if action_id == "scan_qr":
		var scanned := inspector.current_asset_id if inspector else ""
		OS.shell_open(passport_url(scanned if scanned != "" else asset_id_for(tag)))
		return
	var container: int = {"KLTA01": 1, "KLTB01": 2}.get(tag, 0)
	if action_id == "complete_exchange" and tasks.exchange_tasks.has(container):
		await tasks.complete(tasks.exchange_tasks[container])
	elif action_id == "exchange":
		commands.write("PLC01.klt_exchange_command", container, true)
	inspector.refresh_actions()


## Resolver URL of a scanned Digital Link (QR content = globalAssetId): its path re-based onto the
## configured GS1 resolver, which redirects to the passport page (ADR-0023).
func passport_url(digital_link: String) -> String:
	var base: String = DevTools.get_arg("vf-resolver-url", config.get("resolver_url", "http://localhost:8096"))
	return DigitalLink.rebase(digital_link, base)


func _start_feed() -> void:
	var url := DevTools.get_arg("vf-aas-events", "")
	if url == "off":
		return
	if url == "":
		url = _load_json(UNS).get("broker", {}).get("websocket", "ws://localhost:9001")
	var client := MqttClient.new()
	client.client_id = "vf-ui-%06x" % (randi() & 0xFFFFFF)
	secure.apply_mqtt(client)
	feed = AasEventFeed.new(client, config.get("aas_events_topic", "vf/basyx/#"))
	if feed.start(url) != OK:
		feed = null


static func _load_json(path: String) -> Dictionary:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}
