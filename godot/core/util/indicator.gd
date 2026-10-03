class_name Indicator
extends RefCounted
## On/off appearance of a lamp/LED mesh from an imported model: "on" glows in the mesh's colour,
## "off" is a darkened, non-emissive copy.

var _mesh: MeshInstance3D
var _on: Array[Material] = []
var _off: Array[Material] = []
var _state := -1


func _init(mesh: MeshInstance3D, energy := 2.5) -> void:
	_mesh = mesh
	for i in mesh.mesh.get_surface_count():
		var base := mesh.get_active_material(i) as BaseMaterial3D
		var on := base.duplicate() as BaseMaterial3D
		on.emission_enabled = true
		on.emission = base.albedo_color
		on.emission_energy_multiplier = maxf(base.emission_energy_multiplier, energy)
		var off := base.duplicate() as BaseMaterial3D
		off.emission_enabled = false
		off.albedo_color = base.albedo_color.darkened(0.7)
		_on.append(on)
		_off.append(off)


func set_on(on: bool) -> void:
	if int(on) == _state:
		return
	_state = int(on)
	for i in _on.size():
		_mesh.set_surface_override_material(i, _on[i] if on else _off[i])
