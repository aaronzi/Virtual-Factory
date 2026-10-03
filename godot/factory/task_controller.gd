class_name TaskController
extends Node
## Operator side of the BPMN processes in the 3D scene (decided in the M4 review: tasks in the Tasklist AND in
## the scene). Polls Operaton for open user tasks, shows them on the MES terminal and knows which KLT has a
## pending "Exchange KLT" task, so clicking the KLT can complete it.

signal tasks_changed

const EXCHANGE_TASK := "User_ExchangeKlt"

var bpmn: BpmnTasks
var view: TaskTerminalView
var panel: WorldPanel
var poll_s := 2.0
var tasks: Array = []
var exchange_tasks := {}  # container (1/2) -> task id
var _timer := 0.0
var _busy := false
var _container_of := {}  # task id -> container (cached)


func setup(p_bpmn: BpmnTasks, root: Node3D, position: Vector3, yaw_deg := 0.0) -> void:
	bpmn = p_bpmn
	view = TaskTerminalView.new()
	view.task_selected.connect(_on_selected)
	view.complete_pressed.connect(func(id: String, values: Dictionary) -> void: complete(id, values))
	panel = WorldPanel.new()
	panel.size_m = Vector2(0.8, 0.5)
	panel.refresh_hz = 1.0
	panel.set_content(view)
	root.add_child(panel)
	panel.position = position + Vector3(0, 1.35, 0)
	panel.rotation_degrees.y = yaw_deg
	panel.add_child(_stand())


func _process(delta: float) -> void:
	_timer -= delta
	if _timer <= 0.0 and not _busy:
		_timer = poll_s
		_poll()


func complete(task_id: String, values := {}) -> void:
	view.set_status(tr("TASKS_COMPLETING"))
	var ok := await bpmn.complete(task_id, values)
	view.set_status(tr("TASKS_DONE") if ok else tr("TASKS_FAILED"))
	_timer = 0.0


func _poll() -> void:
	_busy = true
	var fresh := await bpmn.list_tasks()
	var exchange := {}
	for t: Dictionary in fresh:
		if t.get("taskDefinitionKey") == EXCHANGE_TASK:
			if not _container_of.has(t.id):
				_container_of[t.id] = int((await bpmn.variables(t.id)).get("container", 0))
			exchange[_container_of[t.id]] = t.id
	var changed := fresh.size() != tasks.size() or exchange != exchange_tasks
	tasks = fresh
	exchange_tasks = exchange
	view.set_tasks(tasks)
	view.set_status(tr("TASKS_COUNT") % tasks.size())
	_busy = false
	if changed:
		tasks_changed.emit()


func _on_selected(task_id: String) -> void:
	var task: Dictionary = {}
	for t: Dictionary in tasks:
		if t.id == task_id:
			task = t
	var form := await bpmn.form_variables(task_id)
	var info := String(task.get("description", "")) if task.get("description") != null else ""
	if task.get("taskDefinitionKey") == EXCHANGE_TASK:
		info = tr("TASKS_EXCHANGE_HINT") % ("A" if _container_of.get(task_id, 1) == 1 else "B")
	view.show_task(task, info, form)


func _stand() -> MeshInstance3D:
	var pole := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.03
	mesh.bottom_radius = 0.03
	mesh.height = 1.1
	pole.mesh = mesh
	pole.position = Vector3(0, -0.8, -0.04)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.62, 0.64, 0.66)
	mat.metallic = 0.6
	pole.material_override = mat
	pole.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return pole
