class_name KltGeometry
extends RefCounted
## Geometry of a VDA KLT 6428 (600 × 400 × 280 mm) on a stand. Device origin = floor below the box
## centre; the long side runs along local Z.

const OUTER := Vector3(0.4, 0.28, 0.6)
const WALL := 0.02


static func floor_height(g: Dictionary) -> float:
	return g.get("stand_height", 0.55) + WALL


## Slot frame (palletizing corners) at robot TCP height: origin, end of first row, end of first column.
static func slot_corners(g: Dictionary) -> Array[Vector3]:
	var y: float = floor_height(g) + g.get("pick_height", 0.15) + 0.005
	var half_x: float = g.get("slot_span_x", 0.2) * 0.5
	var half_z: float = g.get("slot_span_z", 0.36) * 0.5
	return [Vector3(-half_x, y, -half_z), Vector3(-half_x, y, half_z), Vector3(half_x, y, -half_z)]
