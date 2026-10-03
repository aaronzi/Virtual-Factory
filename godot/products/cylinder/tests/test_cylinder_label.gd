extends GutTest
## The cylinder's type plate shows the QR code of the part's GS1 Digital Link on the existing label surface.

const SCENE := preload("res://products/cylinder/cylinder_workpiece.tscn")
const LINK := "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000042"


func test_part_carries_its_digital_link_as_qr_on_the_label() -> void:
	var part: TrackedItem = SCENE.instantiate()
	add_child_autofree(part)
	var body := part.find_child("Body", true, false) as MeshInstance3D
	var surfaces := body.mesh.get_surface_count()
	var label: CylinderLabel = part.get("_label")
	var product_qr := label.current_texture()
	assert_not_null(product_qr, "product (GTIN) QR until the serial is known")
	part.configure("PC3280-2026-000042", {"cap_variant": 0})
	assert_eq(part.get_asset_id(), LINK)
	label.finish()
	await wait_process_frames(2)  # deferred apply on the main thread
	var texture := label.current_texture()
	assert_ne(texture, product_qr)
	var expected := QrCode.encode(LINK).to_image(CylinderLabel.QUIET_ZONE)
	var image := texture.get_image()
	image.clear_mipmaps()
	assert_eq(image.get_data(), expected.get_data(), "texture = module matrix of the Digital Link")
	assert_eq(body.mesh.get_surface_count(), surfaces, "no additional surface (draw call)")
	assert_true(body.get_surface_override_material(CylinderLabel._label_surface(body)) is ShaderMaterial)
