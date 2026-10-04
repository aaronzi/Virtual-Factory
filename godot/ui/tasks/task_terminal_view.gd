class_name TaskTerminalView
extends PanelContainer
## Shop-floor MES terminal: the operator's open BPMN user tasks (same as the Operaton Tasklist), with the form
## fields of the selected task and a "complete" button. View only.

signal task_selected(task_id: String)
signal complete_pressed(task_id: String, values: Dictionary)

const LONG_TEXT := 32  # form values longer than this get a multi-line field

var _list: ItemList
var _title: Label
var _info: Label
var _form: GridContainer
var _complete: Button
var _status: Label
var _task_ids: Array[String] = []
var _selected := ""
var _fields := {}  # name -> Control


func _init() -> void:
	theme = UiTheme.get_theme()
	var root := VBoxContainer.new()
	add_child(root)
	root.add_child(UiTheme.label("TASKS_TITLE", 26))
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_list = ItemList.new()
	_list.custom_minimum_size = Vector2(300, 120)
	_list.item_selected.connect(func(i: int) -> void: task_selected.emit(_task_ids[i]))
	body.add_child(_list)
	# the task description and form can be longer than the panel: scrollable (wheel/trackpad/thumbstick)
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var detail := VBoxContainer.new()
	detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title = UiTheme.label("", 24)
	_info = UiTheme.label("TASKS_NONE", 18, UiTheme.MUTED)
	_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_form = GridContainer.new()
	_form.columns = 2
	_form.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_complete = Button.new()
	_complete.text = "TASKS_COMPLETE"
	_complete.disabled = true
	_complete.pressed.connect(_on_complete)
	for c in [_title, _info, _form, _complete]:
		detail.add_child(c)
	scroll.add_child(detail)
	body.add_child(scroll)
	root.add_child(body)
	_status = UiTheme.label("", 16, UiTheme.MUTED)
	root.add_child(_status)


## tasks: [{id, name, created, processName?}] in display order.
func set_tasks(tasks: Array) -> void:
	var ids: Array[String] = []
	for t: Dictionary in tasks:
		ids.append(t.id)
	if ids == _task_ids:
		return
	_task_ids = ids
	_list.clear()
	for t: Dictionary in tasks:
		_list.add_item("%s · %s" % [String(t.get("created", "")).substr(11, 5), t.get("name", "?")])
	if _selected in _task_ids:
		_list.select(_task_ids.find(_selected))
	elif not _task_ids.is_empty():
		_list.select(0)
		task_selected.emit(_task_ids[0])  # show the oldest open task right away
	else:
		_clear_detail()


## Shows a task; form: {name: {type, value}} from the engine's form variables.
func show_task(task: Dictionary, info: String, form: Dictionary) -> void:
	_selected = task.id
	_title.text = task.get("name", "")
	_info.text = info
	for child in _form.get_children():
		child.queue_free()
	_fields.clear()
	for name: String in form:
		var label := UiTheme.label(name, 18, UiTheme.MUTED)
		label.size_flags_vertical = Control.SIZE_SHRINK_BEGIN  # next to the first line of multi-line values
		_form.add_child(label)
		var field := _field(String(form[name].get("type", "String")), form[name].get("value"))
		_form.add_child(field)
		_fields[name] = field
	_complete.disabled = false


func set_status(text: String) -> void:
	_status.text = text


func _on_complete() -> void:
	var values := {}
	for name: String in _fields:
		var f: Control = _fields[name]
		values[name] = f.button_pressed if f is CheckBox else int(f.value) if f is SpinBox else f.text
	_complete.disabled = true
	complete_pressed.emit(_selected, values)


func _clear_detail() -> void:
	_selected = ""
	_title.text = ""
	_info.text = "TASKS_NONE" if _task_ids.is_empty() else "TASKS_SELECT"
	for child in _form.get_children():
		child.queue_free()
	_fields.clear()
	_complete.disabled = true


static func _field(type: String, value: Variant) -> Control:
	match type:
		"Boolean":
			var c := CheckBox.new()
			c.button_pressed = bool(value) if value != null else false
			return c
		"Long", "Integer":
			var s := SpinBox.new()
			s.max_value = 1e6
			s.value = float(value) if value != null else 0.0
			return s
	var text := str(value) if value != null else ""
	if text.length() > LONG_TEXT or "\n" in text:  # e.g. maintenance instructions: wrapped, all lines visible
		var t := TextEdit.new()
		t.text = text
		t.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
		t.scroll_fit_content_height = true
		t.custom_minimum_size.x = 260
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		return t
	var e := LineEdit.new()
	e.text = text
	e.custom_minimum_size.x = 260
	return e
