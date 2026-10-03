class_name DataFlowView
extends Node3D
## Education mode: the IT layer as labelled nodes above the line and packets that travel along the real data
## paths when real messages occur (driven by a controller: UNS events, BaSyx change events).

const PACKET_SPEED := 2.2  # m/s
const MAX_PACKETS := 48
const NODE_COLOR := Color(0.18, 0.55, 0.95)

var nodes := {}  # name -> Vector3 (world)
var _packets: Array[Dictionary] = []  # {mesh, points, leg, t}
var _sphere := SphereMesh.new()


func _init() -> void:
	_sphere.radius = 0.045
	_sphere.height = 0.09


## Adds (or moves) a node; `label` empty = invisible waypoint (e.g. a device).
func add_node(node_name: String, position_w: Vector3, label := "") -> void:
	nodes[node_name] = position_w
	if label == "":
		return
	var box := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.34, 0.2, 0.08)
	box.mesh = mesh
	box.material_override = _emissive(NODE_COLOR, 0.25)
	box.position = position_w
	add_child(box)
	var text := Label3D.new()
	text.text = label
	text.font_size = 40
	text.pixel_size = 0.0025
	text.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	text.outline_size = 10
	text.position = position_w + Vector3(0, 0.2, 0)
	add_child(text)


## Draws a thin static link between two nodes (topology of the IT layer).
func add_link(a: String, b: String) -> void:
	if not (nodes.has(a) and nodes.has(b)):
		return
	var lines := ImmediateMesh.new()
	lines.surface_begin(Mesh.PRIMITIVE_LINES)
	lines.surface_add_vertex(nodes[a])
	lines.surface_add_vertex(nodes[b])
	lines.surface_end()
	var mesh := MeshInstance3D.new()
	mesh.mesh = lines
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = NODE_COLOR.lightened(0.3)
	mesh.material_override = mat
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mesh)


## Sends a packet along the named nodes (unknown names are skipped).
func pulse(path: Array, color := Color(1.0, 0.6, 0.15)) -> void:
	var points: Array[Vector3] = []
	for n: String in path:
		if nodes.has(n):
			points.append(nodes[n])
	if points.size() < 2 or _packets.size() >= MAX_PACKETS or not visible:
		return
	var mesh := MeshInstance3D.new()
	mesh.mesh = _sphere
	mesh.material_override = _emissive(color, 0.9)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mesh.position = points[0]
	add_child(mesh)
	_packets.append({"mesh": mesh, "points": points, "leg": 0, "t": 0.0})


func _process(delta: float) -> void:
	for i in range(_packets.size() - 1, -1, -1):
		var p: Dictionary = _packets[i]
		var a: Vector3 = p.points[p.leg]
		var b: Vector3 = p.points[p.leg + 1]
		p.t += delta * PACKET_SPEED / maxf(a.distance_to(b), 0.05)
		if p.t >= 1.0:
			p.leg += 1
			p.t = 0.0
			if p.leg >= p.points.size() - 1:
				p.mesh.queue_free()
				_packets.remove_at(i)
				continue
			a = p.points[p.leg]
			b = p.points[p.leg + 1]
		p.mesh.position = a.lerp(b, p.t)


static func _emissive(color: Color, energy: float) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = energy
	return mat
