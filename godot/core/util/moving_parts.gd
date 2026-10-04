class_name MovingParts
extends RefCounted
## Marks nodes that move at runtime (robot joints, hinged doors, rotating drums). Baked lighting
## (ADR-0031) keeps marked nodes and everything below them dynamic: they are lit by light probes and
## cast real-time shadows, while all other static geometry uses the lightmap and its shadowmask.

const GROUP := &"vf_moving"


static func mark(node: Node) -> void:
	node.add_to_group(GROUP)


## True if `node` or one of its ancestors is marked as moving.
static func is_moving(node: Node) -> bool:
	while node != null:
		if node.is_in_group(GROUP):
			return true
		node = node.get_parent()
	return false
