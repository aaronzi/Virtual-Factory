class_name MeshMerger
extends RefCounted
## Static batching for the Compatibility renderer: merges the MeshInstance3D descendants of `source`
## into one ArrayMesh with one surface per material (fewer draw calls), expressed in `target`'s space.


static func merge(source: Node3D, target: Node3D, merged_name := "Merged") -> MeshInstance3D:
	var tools := {}  # material -> SurfaceTool
	for mi in _mesh_instances(source):
		var xform := target.global_transform.affine_inverse() * mi.global_transform
		for s in mi.mesh.get_surface_count():
			var mat := mi.get_active_material(s)
			if not tools.has(mat):
				var st := SurfaceTool.new()
				st.begin(Mesh.PRIMITIVE_TRIANGLES)
				tools[mat] = st
			(tools[mat] as SurfaceTool).append_from(mi.mesh, s, xform)
	var mesh := ArrayMesh.new()
	for mat in tools:
		var st: SurfaceTool = tools[mat]
		st.set_material(mat)
		st.commit(mesh)
	var merged := MeshInstance3D.new()
	merged.name = merged_name
	merged.mesh = mesh
	target.add_child(merged)
	return merged


static func _mesh_instances(node: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	for child in node.get_children():
		if child is MeshInstance3D and (child as MeshInstance3D).visible:
			out.append(child)
		out.append_array(_mesh_instances(child))
	return out
