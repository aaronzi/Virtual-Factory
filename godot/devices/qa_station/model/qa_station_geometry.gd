class_name QaStationGeometry
extends RefCounted
## Shared geometry of the QA station (used by probe and view). Device origin = belt top surface at
## the inspection/stop position; the sensor looks at the part top from the +Z side at an angle so the
## space above the part stays free for the robot gripper.


static func inspection_point(g: Dictionary) -> Vector3:
	return Vector3(0, g.get("part_height", 0.235) - 0.005, 0)


static func sensor_head(g: Dictionary) -> Vector3:
	return inspection_point(g) + Vector3(0, g.get("sensor_height", 0.09), g.get("sensor_offset", 0.12))
