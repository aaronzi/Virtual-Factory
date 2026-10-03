class_name MainMenu
extends CanvasLayer
## Desktop menu (Esc or F1 toggles it, desktop-only extra per ADR-0003): language, render quality, simulation
## speed, training scenarios, demo tour, data-flow view. Also shows tour captions.
## View only - emits the user's choices.
## Scenario list entries: {id, title} (already localized by the runner).

signal language_selected(locale: String)
signal quality_selected(preset: int)
signal speed_selected(factor: float)
signal scenario_start(id: String)
signal scenario_stop
signal tour_toggled(on: bool)
signal dataflow_toggled(on: bool)

const SPEEDS := [1.0, 2.0, 4.0]
const WIDTH := 440
const QUALITY_NAMES := ["QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"]  # order of QualitySettings.Preset

var _panel: PanelContainer
var _scenarios: OptionButton
var _scenario_ids: Array[String] = []
var _scenario_status: Label
var _caption: Label
var _band: PanelContainer
var _language: OptionButton
var _tour: CheckButton
var _info: Label


func _ready() -> void:
	layer = 5
	_panel = PanelContainer.new()
	_panel.theme = UiTheme.get_theme()
	_panel.anchor_left = 1.0
	_panel.anchor_right = 1.0
	_panel.anchor_bottom = 1.0
	_panel.offset_left = -WIDTH - 16
	_panel.offset_right = -16
	_panel.offset_top = 16
	_panel.offset_bottom = -16
	_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN  # never past the right window edge
	_panel.visible = false
	add_child(_panel)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_panel.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(box)
	_fill(box)
	add_child(_caption_band())


func open() -> void:
	_panel.visible = true


func _fill(box: VBoxContainer) -> void:
	box.add_child(UiTheme.label("MENU_TITLE", 26))
	var lang_row := _choice("MENU_LANGUAGE", ["English", "Deutsch"], func(i: int) -> void:
		language_selected.emit(["en", "de"][i]))
	_language = lang_row.get_child(1)
	box.add_child(lang_row)
	box.add_child(_choice("MENU_QUALITY", QUALITY_NAMES, func(i: int) -> void: quality_selected.emit(i), 1))
	box.add_child(_choice("MENU_SPEED", ["1×", "2×", "4×"],
		func(i: int) -> void: speed_selected.emit(SPEEDS[i])))
	box.add_child(_scenario_row())
	_tour = _toggle("MENU_TOUR", func(on: bool) -> void: tour_toggled.emit(on))
	box.add_child(_tour)
	box.add_child(_toggle("MENU_DATAFLOW", func(on: bool) -> void: dataflow_toggled.emit(on)))
	_info = UiTheme.label("", 16, UiTheme.MUTED)
	_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_info)
	var hint := UiTheme.label("MENU_HINT", 15, UiTheme.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(hint)


## Tour captions: large text on a dark band at the bottom centre (hidden when empty).
func _caption_band() -> Control:
	_band = PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.05, 0.06, 0.08, 0.82)
	style.set_corner_radius_all(10)
	style.set_content_margin_all(18)
	_band.add_theme_stylebox_override("panel", style)
	_band.anchor_left = 0.5
	_band.anchor_right = 0.5
	_band.anchor_top = 1.0
	_band.anchor_bottom = 1.0
	_band.offset_left = -470
	_band.offset_right = 470
	_band.offset_bottom = -28
	_band.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_band.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_caption = UiTheme.label("", 32)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_band.add_child(_caption)
	_band.visible = false
	return _band


func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key and key.pressed and not key.echo and key.keycode in [KEY_F1, KEY_ESCAPE]:
		_panel.visible = not _panel.visible


func set_scenarios(list: Array) -> void:
	_scenarios.clear()
	_scenario_ids.clear()
	for s: Dictionary in list:
		_scenario_ids.append(s.get("id", ""))
		_scenarios.add_item(s.get("title", s.get("id", "")))


## Reflects state changed elsewhere (dev args, tour end) without emitting signals.
func show_state(locale: String, tour_on: bool) -> void:
	_language.select(1 if locale.begins_with("de") else 0)
	_tour.set_pressed_no_signal(tour_on)


func set_scenario_status(text: String) -> void:
	_scenario_status.text = text


func set_caption(text: String) -> void:
	_caption.text = text
	_band.visible = text != ""


func set_info(text: String) -> void:
	_info.text = text


func _scenario_row() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_child(UiTheme.label("MENU_SCENARIOS", 20, UiTheme.MUTED))
	_scenarios = OptionButton.new()
	_scenarios.fit_to_longest_item = false
	_scenarios.clip_text = true
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
	opt.fit_to_longest_item = false
	opt.clip_text = true
	opt.custom_minimum_size.x = 170
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
