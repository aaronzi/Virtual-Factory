class_name UiTheme
extends RefCounted
## Shared look of the in-world panels: dark industrial HMI style, large fonts (readable at 1-2 m and in VR).

const BG := Color(0.09, 0.1, 0.12)
const PANEL := Color(0.14, 0.16, 0.19)
const TEXT := Color(0.9, 0.93, 0.95)
const MUTED := Color(0.62, 0.67, 0.72)
const ACCENT := Color(0.96, 0.55, 0.13)   # VF orange
const OK := Color(0.3, 0.75, 0.38)
const WARN := Color(0.95, 0.7, 0.2)
const ALARM := Color(0.86, 0.25, 0.22)

static var _theme: Theme


static func get_theme() -> Theme:
	if _theme == null:
		_theme = _make()
	return _theme


static func _make() -> Theme:
	var t := Theme.new()
	t.default_font_size = 22
	t.set_color("font_color", "Label", TEXT)
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_color", "Tree", TEXT)
	t.set_color("font_color", "ItemList", TEXT)
	t.set_stylebox("panel", "PanelContainer", _box(BG, 0))
	t.set_stylebox("panel", "Tree", _box(PANEL, 4))
	t.set_stylebox("panel", "ItemList", _box(PANEL, 4))
	t.set_stylebox("normal", "Button", _box(Color(0.22, 0.25, 0.29), 6))
	t.set_stylebox("hover", "Button", _box(Color(0.3, 0.34, 0.39), 6))
	t.set_stylebox("pressed", "Button", _box(ACCENT.darkened(0.2), 6))
	t.set_stylebox("disabled", "Button", _box(Color(0.17, 0.18, 0.2), 6))
	t.set_stylebox("normal", "LineEdit", _box(PANEL.lightened(0.08), 4))
	t.set_constant("v_separation", "Tree", 6)
	t.set_constant("separation", "VBoxContainer", 10)
	t.set_constant("separation", "HBoxContainer", 10)
	return t


static func _box(color: Color, radius: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = color
	box.set_corner_radius_all(radius)
	box.set_content_margin_all(10)
	return box


## A label with a font size and colour (helper for code-built panels).
static func label(text: String, size := 22, color := TEXT) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l
