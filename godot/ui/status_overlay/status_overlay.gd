extends CanvasLayer
## Desktop status overlay (screen-space, desktop-only extra per ADR-0003). Shows the text returned
## by `source`, refreshed a few times per second.

var source: Callable
var _label: Label
var _timer := 0.0


func _ready() -> void:
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 16)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.1, 0.12, 0.78)
	style.set_content_margin_all(12)
	style.set_corner_radius_all(6)
	panel.add_theme_stylebox_override("panel", style)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 15)
	_label.add_theme_color_override("font_color", Color(0.9, 0.93, 0.95))
	panel.add_child(_label)
	add_child(panel)


func _process(delta: float) -> void:
	_timer -= delta
	if _timer > 0.0 or not source.is_valid():
		return
	_timer = 0.25
	_label.text = source.call()
