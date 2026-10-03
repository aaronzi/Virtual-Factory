class_name MainMenu
extends CanvasLayer
## Desktop menu (F1, desktop-only extra per ADR-0003): language, render quality, simulation speed, training
## scenarios, demo tour, data-flow view. Also shows tour captions. View only - emits the user's choices.
## Scenario list entries: {id, title} (already localized by the runner).

signal language_selected(locale: String)
signal quality_selected(preset: int)
signal speed_selected(factor: float)
signal scenario_start(id: String)
signal scenario_stop
signal tour_toggled(on: bool)
signal dataflow_toggled(on: bool)

const SPEEDS := [1.0, 2.0, 4.0]
const QUALITY_NAMES := ["QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"]  # order of QualitySettings.Preset

var _panel: PanelContainer
var _scenarios: OptionButton
var _scenario_ids: Array[String] = []
var _scenario_status: Label
var _caption: Label
var _info: Label


func _ready() -> void:
	layer = 5
	_panel = PanelContainer.new()
	_panel.theme = UiTheme.get_theme()
	_panel.anchor_left = 1.0
	_panel.anchor_right = 1.0
	_panel.offset_left = -430
	_panel.offset_top = 16
	_panel.offset_right = -16
	_panel.visible = false
	add_child(_panel)
	var box := VBoxContainer.new()
	_panel.add_child(box)
	box.add_child(UiTheme.label("MENU_TITLE", 26))
	box.add_child(_choice("MENU_LANGUAGE", ["English", "Deutsch"], func(i: int) -> void:
		language_selected.emit(["en", "de"][i])))
	box.add_child(_choice("MENU_QUALITY", QUALITY_NAMES, func(i: int) -> void: quality_selected.emit(i), 1))
	box.add_child(_choice("MENU_SPEED", ["1×", "2×", "4×"],
		func(i: int) -> void: speed_selected.emit(SPEEDS[i])))
	box.add_child(_scenario_row())
	box.add_child(_toggle("MENU_TOUR", func(on: bool) -> void: tour_toggled.emit(on)))
	box.add_child(_toggle("MENU_DATAFLOW", func(on: bool) -> void: dataflow_toggled.emit(on)))
	_info = UiTheme.label("", 16, UiTheme.MUTED)
	box.add_child(_info)
	box.add_child(UiTheme.label("MENU_HINT", 15, UiTheme.MUTED))
	_caption = UiTheme.label("", 24)
	_caption.theme = UiTheme.get_theme()
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_caption.anchor_top = 1.0
	_caption.anchor_bottom = 1.0
	_caption.anchor_right = 1.0
	_caption.offset_top = -120
	_caption.offset_left = 200
	_caption.offset_right = -200
	_caption.add_theme_color_override("font_outline_color", Color.BLACK)
	_caption.add_theme_constant_override("outline_size", 8)
	add_child(_caption)


func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key and key.pressed and not key.echo and key.keycode in [KEY_F1, KEY_ESCAPE]:
		_panel.visible = not _panel.visible if key.keycode == KEY_F1 else false


func set_scenarios(list: Array) -> void:
	_scenarios.clear()
	_scenario_ids.clear()
	for s: Dictionary in list:
		_scenario_ids.append(s.get("id", ""))
		_scenarios.add_item(s.get("title", s.get("id", "")))


func set_scenario_status(text: String) -> void:
	_scenario_status.text = text


func set_caption(text: String) -> void:
	_caption.text = text


func set_info(text: String) -> void:
	_info.text = text


func _scenario_row() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_child(UiTheme.label("MENU_SCENARIOS", 20, UiTheme.MUTED))
	_scenarios = OptionButton.new()
	box.add_child(_scenarios)
	var row := HBoxContainer.new()
	var start := Button.new()
	start.text = "MENU_START"
	start.pressed.connect(func() -> void:
		if _scenarios.selected >= 0:
			scenario_start.emit(_scenario_ids[_scenarios.selected]))
	var stop := Button.new()
	stop.text = "MENU_STOP"
	stop.pressed.connect(func() -> void: scenario_stop.emit())
	row.add_child(start)
	row.add_child(stop)
	box.add_child(row)
	_scenario_status = UiTheme.label("", 16, UiTheme.MUTED)
	_scenario_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_scenario_status)
	return box


static func _choice(title: String, items: Array, on_select: Callable, selected := 0) -> HBoxContainer:
	var row := HBoxContainer.new()
	var label := UiTheme.label(title, 20, UiTheme.MUTED)
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)
	var opt := OptionButton.new()
	for item: String in items:
		opt.add_item(item)
	opt.select(selected)
	opt.item_selected.connect(on_select)
	row.add_child(opt)
	return row


static func _toggle(title: String, on_toggle: Callable) -> CheckButton:
	var b := CheckButton.new()
	b.text = title
	b.toggled.connect(on_toggle)
	return b
