class_name CameraTour
extends Node
## Demo mode: flies the player rig along the stops of a tour (res://config/tours/*.json) with captions in the
## current language. A stop may name an asset whose AAS is opened (`inspect`), via the `stop_reached` signal.

signal stop_reached(stop: Dictionary)
signal caption_changed(text: String)
signal finished

var rig: PlayerRig
var stops: Array = []
var loop := true
var active := false
var _index := -1
var _t := 0.0
var _from_pos := Vector3.ZERO
var _from_target := Vector3.ZERO
var _target := Vector3.ZERO


func load_tour(path: String) -> bool:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	stops = data.get("stops", []) if data is Dictionary else []
	return not stops.is_empty()


func start() -> void:
	if stops.is_empty() or rig == null:
		return
	active = true
	var cam := rig.get_view_camera()
	_target = cam.global_position - cam.global_basis.z * 3.0
	_next()


func stop() -> void:
	active = false
	caption_changed.emit("")


func _process(delta: float) -> void:
	if not active:
		return
	var stop: Dictionary = stops[_index]
	var fly: float = stop.get("fly_s", 4.0)
	_t += delta
	var k := smoothstep(0.0, 1.0, minf(_t / fly, 1.0))
	rig.teleport_to(_from_pos.lerp(_vec(stop.position), k), _from_target.lerp(_vec(stop.target), k))
	if _t >= fly + float(stop.get("hold_s", 6.0)):
		if _index == stops.size() - 1 and not loop:
			stop()
			finished.emit()
		else:
			_next()


func _next() -> void:
	var cam := rig.get_view_camera()
	_from_pos = rig.global_position
	_from_target = _target if _index < 0 else _vec(stops[_index].target)
	_index = (_index + 1) % stops.size()
	_t = 0.0
	var stop: Dictionary = stops[_index]
	_target = _vec(stop.target)
	var lang := TranslationServer.get_locale().substr(0, 2)
	caption_changed.emit("%d/%d  ·  %s" % [_index + 1, stops.size(),
		stop.get("caption_" + lang, stop.get("caption_en", ""))])
	stop_reached.emit(stop)
	if cam == null:
		push_warning("CameraTour: rig has no camera")


static func _vec(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])
