class_name TrainingUi
extends Node
## Composition of the in-world training UI (part of the composition root): pointer routing, asset picking,
## AAS inspector with BaSyx events, and the backend clients. Endpoints: res://config/backend.json,
## `--vf-aas-url=`, `--vf-bpmn-url=`, `--vf-aas-events=<broker url|off>` (default: broker of uns.json),
## `--vf-inspect=<AAS tag>` opens the inspector at start (screenshots, demos).

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


func setup(p_factory: Node, p_rig: PlayerRig) -> void:
	factory = p_factory
	rig = p_rig
	config = _load_json(BACKEND)
	aas = AasClient.new()
	aas.base_url = DevTools.get_arg("vf-aas-url", config.get("aas_url", "http://localhost:8091"))
	aas.id_base = config.get("id_base", aas.id_base)
	add_child(aas)
	_start_feed()
	router = PointerRouter.new()
	add_child(router)
	router.rig = rig
	router.world_pressed.connect(_on_world_pressed)
	AssetPicker.add_volumes(factory.builder)
	inspector = InspectorController.new()
	add_child(inspector)
	inspector.setup(aas, feed, rig)
	inspector.actions_provider = _actions_for
	inspector.action_handler = _on_action
	commands = LocalCommands.new(factory.builder.master)
	process_physics_priority = -10  # local commands are applied before the factory steps the co-simulation
	_setup_hmi()
	_setup_tasks()
	dataflow = DataFlowController.new()
	add_child(dataflow)
	dataflow.setup(factory.builder, factory.get("uns"), feed)
	menu = MenuController.new()
	add_child(menu)
	menu.setup(self)
	var inspect := DevTools.get_arg("vf-inspect")
	if inspect != "":
		get_tree().create_timer(1.0).timeout.connect(func() -> void: inspector.open_asset(inspect))


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
		inspector.open_asset(picked.tag)


func set_dataflow(on: bool) -> void:
	dataflow.set_visible(on)


func _setup_hmi() -> void:
	for prop: Node3D in factory.builder.props:
		if prop.scene_file_path.ends_with("hmi_stand.glb"):
			hmi = HmiController.new()
			add_child(hmi)
			hmi.setup(factory.builder.master, commands, prop)
			return


func _setup_tasks() -> void:
	var bpmn := BpmnTasks.new()
	bpmn.base_url = DevTools.get_arg("vf-bpmn-url", config.get("bpmn_url", bpmn.base_url))
	add_child(bpmn)
	tasks = TaskController.new()
	tasks.poll_s = config.get("task_poll_s", 2.0)
	add_child(tasks)
	var pos: Array = config.get("terminal_position", [1.65, 0.0, 0.25])
	tasks.setup(bpmn, factory, Vector3(pos[0], pos[1], pos[2]), config.get("terminal_yaw_deg", 40.0))
	tasks.tasks_changed.connect(inspector.refresh_actions)


## Context actions of the inspector: KLT stations offer the exchange (BPMN task or direct command).
func _actions_for(tag: String) -> Array:
	var container: int = {"KLTA01": 1, "KLTB01": 2}.get(tag, 0)
	if container == 0:
		return []
	if tasks and tasks.exchange_tasks.has(container):
		return [{"id": "complete_exchange", "label": tr("KLT_EXCHANGE_TASK")}]
	return [{"id": "exchange", "label": tr("KLT_EXCHANGE_NOW")}]


func _on_action(tag: String, action_id: String) -> void:
	var container: int = {"KLTA01": 1, "KLTB01": 2}.get(tag, 0)
	if action_id == "complete_exchange" and tasks.exchange_tasks.has(container):
		await tasks.complete(tasks.exchange_tasks[container])
	elif action_id == "exchange":
		commands.write("PLC01.klt_exchange_command", container, true)
	inspector.refresh_actions()


func _start_feed() -> void:
	var url := DevTools.get_arg("vf-aas-events", "")
	if url == "off":
		return
	if url == "":
		url = _load_json(UNS).get("broker", {}).get("websocket", "ws://localhost:9001")
	var client := MqttClient.new()
	client.client_id = "vf-ui-%06x" % (randi() & 0xFFFFFF)
	feed = AasEventFeed.new(client, config.get("aas_events_topic", "vf/basyx/#"))
	if feed.start(url) != OK:
		feed = null


static func _load_json(path: String) -> Dictionary:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}
