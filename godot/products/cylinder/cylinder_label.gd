class_name CylinderLabel
extends RefCounted
## QR code of the part's GS1 Digital Link on the cylinder's type plate (ADR-0023). The imported label material
## of the Body mesh is replaced by a shader material on the same surface (label texture shared, a 45x45 QR
## texture per part), so the QR costs no extra draw call. Encoding (~13 ms) runs on a worker thread; until it
## is done the label shows the QR of the product type (GTIN link).

const SHADER := preload("res://products/cylinder/label_qr.gdshader")
const LABEL_MATERIAL := "decal_typeplate_cylinder"
const QUIET_ZONE := 4

static var _product_qr := {}  # product link -> ImageTexture (shared by all parts)

var material: ShaderMaterial
var link := ""
var _task := -1


func _init(body: MeshInstance3D, product_link: String) -> void:
	var surface := _label_surface(body)
	if surface < 0:
		push_warning("CylinderLabel: no surface with material %s" % LABEL_MATERIAL)
		return
	var imported := body.mesh.surface_get_material(surface) as BaseMaterial3D
	material = ShaderMaterial.new()
	material.shader = SHADER
	material.set_shader_parameter("label_texture", imported.albedo_texture)
	material.set_shader_parameter("roughness", imported.roughness)
	if not _product_qr.has(product_link):
		_product_qr[product_link] = texture_for(QrCode.encode(product_link))
	material.set_shader_parameter("qr_texture", _product_qr[product_link])
	body.set_surface_override_material(surface, material)


## Shows the QR code of `uri` (the label keeps the previous code until the worker has encoded it).
func show_link(uri: String) -> void:
	if uri == link or material == null:
		return
	link = uri
	finish()
	_task = WorkerThreadPool.add_task(_encode.bind(uri), false, "QR " + uri.get_file())


## Waits for a running encoding (before the owner leaves the tree).
func finish() -> void:
	if _task >= 0:
		WorkerThreadPool.wait_for_task_completion(_task)
		_task = -1


func current_texture() -> Texture2D:
	return material.get_shader_parameter("qr_texture") if material else null


static func texture_for(qr: QrCode) -> ImageTexture:
	if qr == null:
		return null
	var image := qr.to_image(QUIET_ZONE)
	image.generate_mipmaps()
	return ImageTexture.create_from_image(image)


func _encode(uri: String) -> void:  # worker thread: pure data only
	var qr := QrCode.encode(uri)
	_apply.call_deferred(uri, qr)


func _apply(uri: String, qr: QrCode) -> void:
	finish()
	if uri == link and qr != null:
		material.set_shader_parameter("qr_texture", texture_for(qr))


static func _label_surface(body: MeshInstance3D) -> int:
	if body == null or body.mesh == null:
		return -1
	for s in body.mesh.get_surface_count():
		var mat := body.mesh.surface_get_material(s)
		if mat and mat.resource_name == LABEL_MATERIAL:
			return s
	return -1
